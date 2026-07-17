from google.genai import types

from prompts import SYSTEM_MESSAGE, get_user_message

from ..utils import (
    EXPECTED_INFERENCE_ERRORS,
    PRO_MODEL,
    generate_content_stream,
    inference_failure_result,
    success_result_from_payload,
)


async def run_pro_model(word, salt=None, timeout=180):
    """Strategy 5: Pro model — testing the community claim with Streaming TTFT."""
    system_instruction = SYSTEM_MESSAGE
    if salt:
        system_instruction += f"\n\nBenchmark Salt: {salt}"

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
    )

    try:
        response = await generate_content_stream(
            model=PRO_MODEL,
            contents=get_user_message(word),
            config=config,
            timeout=timeout,
        )
    except EXPECTED_INFERENCE_ERRORS as e:
        return inference_failure_result(e)
    return success_result_from_payload(response, model=PRO_MODEL)
