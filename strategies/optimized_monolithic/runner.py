import asyncio

from google.genai import types
from ..utils import (
    FLASH_MODEL,
    _extract_usage,
    estimate_cost,
    generate_content_stream,
)
from prompts import get_user_message, OPTIMIZED_SYSTEM_MESSAGE

async def run_optimized(word, salt=None, timeout=120):
    """Estrategia: Prompt de Sistema Optimizado con Temperatura Cero y TTFT por streaming."""
    system_instruction = OPTIMIZED_SYSTEM_MESSAGE
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
            contents=get_user_message(word),
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
            "error": str(e),
        }
