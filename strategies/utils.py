import asyncio
import os
import random
import time

from google import genai
from google.genai import errors as genai_errors

from .providers import GeminiProvider, InferenceProvider

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

# --- Capa de resiliencia/concurrencia (Fase 2) -------------------------------
#
# La medicion (`medicion_fase2.md`) confirmo que el fan-out de `cascade` lanza
# in-flight == nº de meanings sin tope, y que un caller concurrente lo escala a
# W·M (100 con 20 palabras × 5 acepciones). El Semaphore va aca, envolviendo la
# llamada REAL a la API en `generate_content_sync`/`_stream`, NO el `gather` por
# palabra: asi el tope cubre tambien el escenario caller-concurrente (W·M), no
# solo el intra-palabra (M).
#
# Limite configurable via env `GEMINI_MAX_CONCURRENCY` (default 5: debajo del
# free tier de 10 RPM con margen; subir en paid). El Semaphore se crea perezoso
# y ligado al event loop activo para no atarse a un loop ya cerrado entre tests.

DEFAULT_MAX_CONCURRENCY = 5


def _read_max_concurrency() -> int:
    raw = os.environ.get("GEMINI_MAX_CONCURRENCY")
    if not raw:
        return DEFAULT_MAX_CONCURRENCY
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_CONCURRENCY
    return value if value > 0 else DEFAULT_MAX_CONCURRENCY


_semaphore: asyncio.Semaphore | None = None
_semaphore_loop: asyncio.AbstractEventLoop | None = None
_semaphore_limit: int | None = None


def get_inference_semaphore() -> asyncio.Semaphore:
    """Semaphore compartido por proceso que capea las requests in-flight.

    Se crea perezoso y se recrea si cambio el event loop activo (p. ej. entre
    ``asyncio.run`` de tests distintos) o el limite configurado. Un
    ``asyncio.Semaphore`` queda ligado al loop donde se construye, por eso no se
    instancia a nivel de modulo.
    """
    global _semaphore, _semaphore_loop, _semaphore_limit
    loop = asyncio.get_running_loop()
    limit = _read_max_concurrency()
    if _semaphore is None or _semaphore_loop is not loop or _semaphore_limit != limit:
        _semaphore = asyncio.Semaphore(limit)
        _semaphore_loop = loop
        _semaphore_limit = limit
    return _semaphore


def reset_inference_semaphore() -> None:
    """Resetea el Semaphore cacheado (util en tests que cambian el limite)."""
    global _semaphore, _semaphore_loop, _semaphore_limit
    _semaphore = None
    _semaphore_loop = None
    _semaphore_limit = None


def _is_transient(exc: Exception) -> bool:
    """¿El error amerita reintento? 429/5xx/timeout = transitorio; 4xx = fatal.

    Un ``APIError`` con ``code`` 429 o >=500 es transitorio (rate limit / fallo
    del servidor); cualquier otro 4xx (400/401/403/404) es fatal (config / auth /
    request mal armado) y reintentar solo desperdicia cuota. Los timeouts se
    tratan como transitorios.
    """
    if isinstance(exc, asyncio.TimeoutError):
        return True
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        if code is None:
            return False
        return code == 429 or code >= 500
    return False


def _retry_after_seconds(exc: Exception) -> float | None:
    """Lee ``Retry-After`` del header de un 429/503 si viene; si no, None.

    El SDK guarda la respuesta httpx/requests en ``exc.response``. El header
    puede ser segundos (entero) o una fecha HTTP; aca solo se soporta el formato
    en segundos (el comun en 429), tolerando ausencia/parse fallido.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        raw = headers.get("Retry-After") or headers.get("retry-after")
    except AttributeError:
        return None
    if not raw:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


async def with_retries(
    coro_factory,
    *,
    max_attempts: int = 4,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    sleep=asyncio.sleep,
):
    """Ejecuta ``coro_factory()`` con backoff exponencial + jitter ante transitorios.

    - ``coro_factory`` es un callable sin args que devuelve una corrutina fresca
      por intento (no se puede re-await la misma corrutina).
    - Reintenta solo errores transitorios (``_is_transient``: 429/5xx/timeout).
      Los fatales (4xx de config/auth, o cualquier excepcion inesperada) se
      propagan en el acto.
    - Respeta ``Retry-After`` del header 429 cuando viene; si no, usa
      ``base_delay * 2**intento`` capado a ``max_delay``, con jitter [0, delay).
    - ``sleep`` es inyectable para tests (evita esperas reales).

    Opt-in: los runners pueden activarlo en modo produccion. En modo benchmark
    se deja desactivado para no enmascarar las tasas de fallo reales que el
    artefacto mide (ver `medicion_fase2.md`).
    """
    attempt = 0
    while True:
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001 - se reclasifica abajo
            attempt += 1
            if attempt >= max_attempts or not _is_transient(exc):
                raise
            retry_after = _retry_after_seconds(exc)
            if retry_after is not None:
                delay = min(retry_after, max_delay)
            else:
                backoff = min(base_delay * (2 ** (attempt - 1)), max_delay)
                delay = random.uniform(0, backoff)  # noqa: S311 - jitter, no cripto
            await sleep(delay)


# Provider activo (Fase 3): el framework habla con esta abstraccion, no con el
# SDK directo. Se puede sustituir (otro modelo, un mock) via `set_provider`.
_provider: InferenceProvider = GeminiProvider()


def get_provider() -> InferenceProvider:
    return _provider


def set_provider(provider: InferenceProvider) -> None:
    global _provider
    _provider = provider


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
    """Cliente Gemini sincrono (solo para el warmup one-shot del orquestador)."""
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


async def generate_content_sync(
    model: str,
    contents,
    config,
    timeout: float | None = None,
    *,
    retry: bool = False,
):
    """Run a non-streaming request and return a normalized response payload.

    Uses the provider's async client (``client.aio``) so that
    ``asyncio.wait_for`` can actually cancel the in-flight request on timeout. A
    blocking call wrapped in ``asyncio.to_thread`` would keep running (and
    billing) after the timeout because executor threads are not cancelable.

    La llamada real a la API queda envuelta por el Semaphore compartido
    (`get_inference_semaphore`), de modo que el nº de requests in-flight nunca
    supere el limite configurado, incluso bajo un caller concurrente (W·M). Con
    ``retry=True`` se aplica backoff exponencial + jitter respetando
    ``Retry-After`` ante transitorios (opt-in; off en modo benchmark).
    """
    provider = get_provider()
    semaphore = get_inference_semaphore()
    start = time.time()

    async def _call():
        async with semaphore:
            inner = provider.generate_content(model=model, contents=contents, config=config)
            return await (asyncio.wait_for(inner, timeout=timeout) if timeout else inner)

    if retry:
        response = await with_retries(_call)
    else:
        response = await _call()
    duration = time.time() - start

    return {
        "text": _extract_response_text(response),
        "parsed": getattr(response, "parsed", None),
        "usage": getattr(response, "usage_metadata", None),
        "duration": duration,
        "ttft": None,  # TTFT not measurable without streaming
    }


async def generate_content_stream(
    model: str,
    contents,
    config,
    timeout: float | None = None,
    *,
    retry: bool = False,
):
    """Run a streaming request and return the concatenated text plus usage metadata.

    El Semaphore compartido envuelve toda la sesion de streaming (no solo el
    arranque): una request en stream sigue ocupando una conexion mientras se
    consume, asi que debe contar como un in-flight hasta que termina. Con
    ``retry=True`` se reintenta el arranque ante transitorios (opt-in).
    """
    provider = get_provider()
    semaphore = get_inference_semaphore()
    start = time.time()
    ttft = 0.0
    text_parts = []
    usage = None

    async def consume():
        nonlocal ttft, usage
        async with semaphore:
            stream = await provider.generate_content_stream(
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

    def _attempt():
        return asyncio.wait_for(consume(), timeout=timeout) if timeout else consume()

    if retry:
        await with_retries(_attempt)
    elif timeout:
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
