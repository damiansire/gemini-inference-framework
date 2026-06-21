from google.genai import types

from prompts import LAZY_SYSTEM_MESSAGE, get_lazy_user_message

from ..utils import (
    EXPECTED_INFERENCE_ERRORS,
    FLASH_MODEL,
    _extract_usage,
    estimate_cost,
    generate_content_stream,
    inference_failure_result,
)


async def run_lazy_optimized(word, salt=None, timeout=120):
    """Strategy: Lazy Optimized - Generates only 3 sentences (A1, A2, B1) with Streaming TTFT."""
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
    except EXPECTED_INFERENCE_ERRORS as e:
        return inference_failure_result(e)
