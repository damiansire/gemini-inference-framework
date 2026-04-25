import asyncio

from google.genai import types
from ..utils import (
    FLASH_MODEL,
    _extract_usage,
    estimate_cost,
    generate_content_stream,
)
from prompts import LAZY_SYSTEM_MESSAGE, get_lazy_user_message

async def run_lazy_optimized(word, salt=None, timeout=120):
    """Estrategia: Optimización Perezosa - Genera solo 3 oraciones (A1, A2, B1) con TTFT por streaming."""
    system_instruction = LAZY_SYSTEM_MESSAGE
    if salt:
        system_instruction += f"\n\nBenchmark Salt: {salt}"

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.0,
        response_mime_type="application/json",
    )

    try:
        response = await generate_content_stream(
            model=FLASH_MODEL,
            contents=get_lazy_user_message(word),
            config=config,
            timeout=timeout,
        )
        pt, ct, thought, tt = _extract_usage(response["usage"])

        return {
            "success": True,
            "duration": response["duration"],
            "ttft": response["ttft"],
            "prompt_tokens": pt,
            "candidate_tokens": ct,
            "thought_tokens": thought,
            "total_tokens": tt,
            "cost": estimate_cost(pt, ct + thought),
            "timed_out": False,
            "text_output": response["text"],
        }
    except Exception as e:
        error_message = str(e) or repr(e)
        return {
            "success": False,
            "duration": 0,
            "ttft": 0,
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "thought_tokens": 0,
            "total_tokens": 0,
            "cost": 0,
            "timed_out": isinstance(e, asyncio.TimeoutError),
            "error": error_message,
        }
