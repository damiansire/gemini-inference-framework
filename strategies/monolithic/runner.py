from google.genai import types

from prompts import SYSTEM_MESSAGE, get_user_message

from ..utils import (
    EXPECTED_INFERENCE_ERRORS,
    FLASH_MODEL,
    _extract_usage,
    estimate_cost,
    generate_content_stream,
    generate_content_sync,
    inference_failure_result,
)


async def run_monolithic(word, salt=None, timeout=120):
    """Strategy 1: Original monolithic prompt, no schema, with streaming TTFT."""
    system_instruction = SYSTEM_MESSAGE
    if salt:
        system_instruction += f"\n\nBenchmark Salt: {salt}"

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
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
    except EXPECTED_INFERENCE_ERRORS as e:
        return inference_failure_result(e)


async def run_monolithic_schema(word, salt=None, timeout=120):
    """Strategy 2: Monolithic with strict JSON schema."""
    full_schema = types.Schema(
        type="ARRAY",
        items=types.Schema(
            type="OBJECT",
            properties={
                "englishDefinition": types.Schema(type="STRING"),
                "examples": types.Schema(
                    type="ARRAY",
                    items=types.Schema(
                        type="OBJECT",
                        properties={
                            "sourceFi": types.Schema(type="STRING"),
                            "spokenFi": types.Schema(type="STRING", nullable=True),
                            "level": types.Schema(type="STRING"),
                        },
                        required=["sourceFi", "level"],
                    ),
                ),
                "synonyms": types.Schema(type="ARRAY", items=types.Schema(type="STRING")),
                "antonyms": types.Schema(type="ARRAY", items=types.Schema(type="STRING")),
                "definiendum": types.Schema(
                    type="OBJECT",
                    properties={"en": types.Schema(type="STRING")},
                    required=["en"],
                ),
            },
            required=["englishDefinition", "examples", "synonyms", "antonyms", "definiendum"],
        ),
    )

    system_instruction = SYSTEM_MESSAGE
    if salt:
        system_instruction += f"\n\nBenchmark Salt: {salt}"

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=full_schema,
    )

    try:
        response = await generate_content_sync(
            model=FLASH_MODEL,
            contents=get_user_message(word),
            config=config,
            timeout=timeout,
        )
        payload = response["parsed"] if response["parsed"] is not None else response["text"]
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
            "text_output": payload,
        }
    except EXPECTED_INFERENCE_ERRORS as e:
        return inference_failure_result(e)
