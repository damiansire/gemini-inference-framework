from google.genai import types

from prompts import SYSTEM_MESSAGE, get_user_message

from ..utils import (
    EXPECTED_INFERENCE_ERRORS,
    PRO_MODEL,
    _extract_usage,
    estimate_cost,
    generate_content_stream,
    inference_failure_result,
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
        pt, ct, thought, tt = _extract_usage(response["usage"])

        return {
            "success": True,
            "duration": response["duration"],
            "ttft": response["ttft"],
            "prompt_tokens": pt,
            "candidate_tokens": ct,
            "thought_tokens": thought,
            "total_tokens": tt,
            "cost": estimate_cost(pt, ct + thought, PRO_MODEL),
            "timed_out": False,
            "text_output": response["text"],
        }
    except EXPECTED_INFERENCE_ERRORS as e:
        return inference_failure_result(e)
