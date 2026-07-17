from google.genai import types

from prompts import OPTIMIZED_SYSTEM_MESSAGE, get_user_message

from ..utils import (
    EXPECTED_INFERENCE_ERRORS,
    FLASH_MODEL,
    generate_content_stream,
    inference_failure_result,
    success_result_from_payload,
)


async def run_optimized(word, salt=None, timeout=120):
    """Strategy: Optimized System Prompt with Zero Temperature and Streaming TTFT."""
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
    except EXPECTED_INFERENCE_ERRORS as e:
        return inference_failure_result(e)
    return success_result_from_payload(response)
