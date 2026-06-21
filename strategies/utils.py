import asyncio
import os
import time

from google import genai
from google.genai import errors as genai_errors

FLASH_MODEL = "gemini-3-flash-preview"
PRO_MODEL = "gemini-3.1-pro-preview"

# Errores que un leaf runner SI debe tragar y reportar como "run fallido":
# son fallos esperados de inferencia/red (timeout, o un error de la API de
# Gemini como 429/5xx). Cualquier otra excepcion (GOOGLE_API_KEY ausente,
# error de auth, KeyError/TypeError por un bug de config o programacion) NO
# entra aca a proposito: debe propagar al orquestador, que la loguea con
# traceback en vez de contarla como un fallo de la estrategia y contaminar la
# tasa de exito del benchmark.
#
# ``genai.errors.APIError`` es la base de ``ClientError`` (4xx, incl. 429) y
# ``ServerError`` (5xx) del SDK, asi que cubre los transitorios de API.
EXPECTED_INFERENCE_ERRORS = (asyncio.TimeoutError, genai_errors.APIError)

COST_RATES = {
    FLASH_MODEL: {"input": 0.10, "output": 0.40},
    PRO_MODEL: {"input": 1.25, "output": 5.00},
}


class MetricsTracker:
    """Coroutine-safe (single event loop) metrics accumulator for multi-stage strategies."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self.prompt_tokens = 0
        self.candidate_tokens = 0
        self.thought_tokens = 0
        self.total_tokens = 0
        self.ttft = 0
        self.stage_durations = {}

    async def record(self, stage_name: str, usage, duration: float, ttft: float = 0):
        async with self._lock:
            pt, ct, thought, tt = _extract_usage(usage)

            self.prompt_tokens += pt
            self.candidate_tokens += ct
            self.thought_tokens += thought
            self.total_tokens += tt

            if self.ttft == 0 and ttft is not None and ttft > 0:
                self.ttft = ttft

            if stage_name not in self.stage_durations:
                self.stage_durations[stage_name] = []
            self.stage_durations[stage_name].append(
                {
                    "duration": duration,
                    "ttft": ttft,
                    "prompt_tokens": pt,
                    "candidate_tokens": ct,
                    "thought_tokens": thought,
                    "total_tokens": tt,
                }
            )

    def summary(self):
        return {
            "prompt_tokens": self.prompt_tokens,
            "candidate_tokens": self.candidate_tokens,
            "thought_tokens_est": self.thought_tokens,
            "total_tokens": self.total_tokens,
            "ttft": self.ttft,
            "stage_durations": self.stage_durations,
        }


def estimate_cost(input_tokens, output_tokens, model=FLASH_MODEL):
    rates = COST_RATES.get(model, COST_RATES[FLASH_MODEL])
    return (input_tokens / 1_000_000 * rates["input"]) + (
        output_tokens / 1_000_000 * rates["output"]
    )


def inference_failure_result(exc, **extra):
    """Dict plano de fallo para un error de inferencia ESPERADO.

    Pensado solo para excepciones de ``EXPECTED_INFERENCE_ERRORS`` (timeout o
    error de la API). Aplana el error a string como pide el contrato comun,
    marca ``timed_out`` cuando corresponde, y deja pasar campos extra por
    estrategia (p. ej. ``thinking_level``). Los errores inesperados NO deben
    pasar por aca: se dejan propagar para que el orquestador los loguee.
    """
    return {
        "success": False,
        "duration": 0,
        "ttft": 0,
        "prompt_tokens": 0,
        "candidate_tokens": 0,
        "thought_tokens": 0,
        "total_tokens": 0,
        "cost": 0,
        "timed_out": isinstance(exc, asyncio.TimeoutError),
        "error": str(exc) or repr(exc),
        **extra,
    }


def _create_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    return genai.Client(api_key=api_key)


def _create_async_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    return genai.Client(api_key=api_key)


def _extract_usage(usage):
    """Extract token counts from new SDK usage_metadata."""
    if not usage:
        return 0, 0, 0, 0

    pt = usage.prompt_token_count or 0
    ct = usage.candidates_token_count or 0
    tt = usage.total_token_count or 0
    thought = usage.thoughts_token_count or 0
    return pt, ct, thought, tt


def _extract_response_text(response):
    text = getattr(response, "text", None)
    if text:
        return text

    parts = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                parts.append(part_text)
    return "".join(parts)


async def generate_content_sync(model: str, contents, config, timeout: float | None = None):
    """Run a non-streaming request and return a normalized response payload.

    Uses the SDK async client (``client.aio``) so that ``asyncio.wait_for`` can
    actually cancel the in-flight request on timeout. A blocking call wrapped in
    ``asyncio.to_thread`` would keep running (and billing) after the timeout
    because executor threads are not cancelable.
    """
    client = _create_async_client()
    start = time.time()

    call = client.aio.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    response = await asyncio.wait_for(call, timeout=timeout) if timeout else await call
    duration = time.time() - start

    return {
        "text": _extract_response_text(response),
        "parsed": getattr(response, "parsed", None),
        "usage": getattr(response, "usage_metadata", None),
        "duration": duration,
        "ttft": None,  # TTFT not measurable without streaming
    }


async def generate_content_stream(model: str, contents, config, timeout: float | None = None):
    """Run a streaming request and return the concatenated text plus usage metadata."""
    client = _create_async_client()
    start = time.time()
    ttft = 0.0
    text_parts = []
    usage = None

    async def consume():
        nonlocal ttft, usage
        stream = await client.aio.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            if ttft == 0:
                ttft = time.time() - start
            if chunk.text:
                text_parts.append(chunk.text)
            if chunk.usage_metadata:
                usage = chunk.usage_metadata

    if timeout:
        await asyncio.wait_for(consume(), timeout=timeout)
    else:
        await consume()

    return {
        "text": "".join(text_parts),
        "parsed": None,
        "usage": usage,
        "duration": time.time() - start,
        "ttft": ttft,
    }
