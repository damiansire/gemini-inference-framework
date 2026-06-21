from google.genai import types

from prompts import SYSTEM_MESSAGE, get_user_message

from ..utils import (
    EXPECTED_INFERENCE_ERRORS,
    FLASH_MODEL,
    _extract_usage,
    estimate_cost,
    generate_content_stream,
    inference_failure_result,
)


async def run_thinking_budget(word, salt=None, thinking_level="LOW", timeout=120):
    """Strategy 4: Monolithic with explicit thinking level cap and Streaming TTFT."""
    system_instruction = SYSTEM_MESSAGE
    if salt:
        system_instruction += f"\n\nBenchmark Salt: {salt}"

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
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
            "thinking_level": thinking_level,
        }
    except EXPECTED_INFERENCE_ERRORS as e:
        return inference_failure_result(e, thinking_level=thinking_level)
