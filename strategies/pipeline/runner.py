import json
import time
from datetime import datetime

from google.genai import types

from ..output_validation import parse_payload
from ..utils import FLASH_MODEL, MetricsTracker, generate_content_sync
from prompts import (
    CASCADE_STAGE1_SYSTEM,
    CASCADE_STAGE2_SYSTEM,
    CASCADE_STAGE3_SYSTEM,
)

BASE_EXTRACTION_SCHEMA = types.Schema(
    type="OBJECT",
    properties={
        "meanings": types.Schema(
            type="ARRAY",
            items=types.Schema(
                type="OBJECT",
                properties={
                    "englishDefinition": types.Schema(type="STRING"),
                    "definiendum": types.Schema(type="STRING"),
                    "synonyms": types.Schema(type="ARRAY", items=types.Schema(type="STRING")),
                    "antonyms": types.Schema(type="ARRAY", items=types.Schema(type="STRING")),
                },
                required=["englishDefinition", "definiendum", "synonyms", "antonyms"],
            ),
        )
    },
    required=["meanings"],
)

CEFR_GENERATION_SCHEMA = types.Schema(
    type="OBJECT",
    properties={
        "examples": types.Schema(
            type="ARRAY",
            items=types.Schema(
                type="OBJECT",
                properties={
                    "sourceFi": types.Schema(type="STRING"),
                    "level": types.Schema(
                        type="STRING",
                        enum=["a1", "a2", "b1", "b2", "c1", "c2"],
                    ),
                },
                required=["sourceFi", "level"],
            ),
        )
    },
    required=["examples"],
)

SPOKENFI_TRANSFORMATION_SCHEMA = types.Schema(
    type="OBJECT",
    properties={
        "spoken_examples": types.Schema(
            type="ARRAY",
            items=types.Schema(
                type="OBJECT",
                properties={
                    "spokenFi": types.Schema(type="STRING", nullable=True),
                    "level": types.Schema(
                        type="STRING",
                        enum=["a1", "a2", "b1", "b2", "c1", "c2"],
                    ),
                },
                required=["level"],
            ),
        )
    },
    required=["spoken_examples"],
)


def _parse_structured_response(stage_name, response):
    if response["parsed"] is not None:
        return response["parsed"]
    data, errors = parse_payload(response["text"])
    if errors:
        raise ValueError(f"{stage_name}: {errors[0]}")
    return data


async def _run_stage(
    stage_name: str,
    *,
    prompt: str,
    system_instruction: str,
    response_schema,
    temperature: float,
    timeout: float,
    metrics: MetricsTracker,
):
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=temperature,
    )
    response = await generate_content_sync(
        model=FLASH_MODEL,
        contents=prompt,
        config=config,
        timeout=timeout,
    )
    await metrics.record(stage_name, response["usage"], response["duration"], response["ttft"])
    return _parse_structured_response(stage_name, response)


async def run_pipeline(word="hana", salt=None, timeout=120):
    """Sequential multi-stage baseline without explicit thinking controls."""
    metrics = MetricsTracker()
    e2e_start = time.time()

    print(
        f"      [{datetime.now().strftime('%H:%M:%S')}] [Pipeline] Stage 1: Extracting meanings for '{word}'..."
    )
    stage1_system = CASCADE_STAGE1_SYSTEM
    if salt:
        stage1_system += f"\n\nBenchmark Salt: {salt}"

    base_data = await _run_stage(
        "stage1_extraction",
        prompt=f"Identify all distinct meanings of the Finnish word '{word}'.",
        system_instruction=stage1_system,
        response_schema=BASE_EXTRACTION_SCHEMA,
        temperature=0.2,
        timeout=timeout,
        metrics=metrics,
    )

    final_entry = []

    for idx, meaning in enumerate(base_data["meanings"], start=1):
        definition = meaning["englishDefinition"]
        print(
            f"      [{datetime.now().strftime('%H:%M:%S')}] [Pipeline] Stage 2: CEFR examples for meaning {idx}..."
        )
        stage2_system = CASCADE_STAGE2_SYSTEM
        if salt:
            stage2_system += f"\n\nSalt: {salt}"

        cefr_data = await _run_stage(
            f"stage2_cefr_m{idx}",
            prompt=(
                f"For the Finnish word '{word}' with this specific meaning: '{definition}', "
                "generate exactly 6 example sentences (A1-C2) in standard written Finnish."
            ),
            system_instruction=stage2_system,
            response_schema=CEFR_GENERATION_SCHEMA,
            temperature=0.7,
            timeout=timeout,
            metrics=metrics,
        )

        print(
            f"      [{datetime.now().strftime('%H:%M:%S')}] [Pipeline] Stage 3: SpokenFi transform for meaning {idx}..."
        )
        stage3_system = CASCADE_STAGE3_SYSTEM
        if salt:
            stage3_system += f"\n\nSalt: {salt}"

        stage3_timeout = min(timeout, 45)
        try:
            spoken_data = await _run_stage(
                f"stage3_spoken_m{idx}",
                prompt=(
                    "Transform these standard Finnish sentences into spoken Finnish (puhekieli):\n"
                    f"{json.dumps(cefr_data['examples'], ensure_ascii=False, indent=2)}"
                ),
                system_instruction=stage3_system,
                response_schema=SPOKENFI_TRANSFORMATION_SCHEMA,
                temperature=0.0,
                timeout=stage3_timeout,
                metrics=metrics,
            )
            spoken_map = {
                example["level"].lower(): example.get("spokenFi")
                for example in spoken_data["spoken_examples"]
            }
        except Exception as exc:
            print(
                f"      [{datetime.now().strftime('%H:%M:%S')}] [Pipeline] Stage 3 fallback for meaning {idx}: {str(exc) or type(exc).__name__}"
            )
            spoken_map = {}

        examples = []
        for example in cefr_data["examples"]:
            level = example["level"].lower()
            spoken = spoken_map.get(level)
            if isinstance(spoken, str) and spoken.strip() == example["sourceFi"].strip():
                spoken = None
            examples.append(
                {
                    "sourceFi": example["sourceFi"],
                    "spokenFi": spoken,
                    "level": level,
                }
            )

        final_entry.append(
            {
                "englishDefinition": definition,
                "examples": examples,
                "synonyms": meaning["synonyms"],
                "antonyms": meaning["antonyms"],
                "definiendum": {"en": meaning["definiendum"]},
            }
        )

    summary = metrics.summary()
    summary["e2e_duration"] = time.time() - e2e_start
    summary["mode"] = "pipeline"
    summary["model"] = FLASH_MODEL
    return final_entry, summary


if __name__ == "__main__":
    import asyncio
    import sys

    word = sys.argv[1] if len(sys.argv) > 1 else "hana"
    result, metrics = asyncio.run(run_pipeline(word))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
