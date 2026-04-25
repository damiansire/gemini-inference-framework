import asyncio

from google.genai import types
from ..utils import (
    FLASH_MODEL,
    _extract_usage,
    estimate_cost,
    generate_content_stream,
    generate_content_sync,
)
from prompts import SYSTEM_MESSAGE, get_user_message

async def run_monolithic(word, salt=None, timeout=120):
    """Estrategia 1: Prompt monolítico original, sin schema, con TTFT por streaming."""
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

async def run_monolithic_schema(word, salt=None, timeout=120):
    """Estrategia 2: Monolítica con schema JSON estricto."""
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
