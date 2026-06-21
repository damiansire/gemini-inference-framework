import asyncio
import json
import time
from datetime import datetime

from google.genai import types

from prompts import (
    CASCADE_STAGE1_SYSTEM,
    CASCADE_STAGE2_SYSTEM,
    CASCADE_STAGE3_SYSTEM,
)

from ..output_validation import parse_payload
from ..stage_assembly import assemble_examples, build_spoken_map
from ..utils import FLASH_MODEL, MetricsTracker, generate_content_sync

STAGE1_SCHEMA = types.Schema(
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

STAGE2_SCHEMA = types.Schema(
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

STAGE3_SCHEMA = types.Schema(
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
    thinking_level: str | None,
    timeout: float,
    metrics: MetricsTracker,
):
    config_kwargs = {
        "system_instruction": system_instruction,
        "response_mime_type": "application/json",
        "response_schema": response_schema,
        "temperature": temperature,
    }
    if thinking_level is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)

    response = await generate_content_sync(
        model=FLASH_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
        timeout=timeout,
    )
    await metrics.record(stage_name, response["usage"], response["duration"], response["ttft"])
    return _parse_structured_response(stage_name, response)


async def run_cascade(word: str = "hana", salt: str = None, timeout: float = 120.0):
    metrics = MetricsTracker()
    e2e_start = time.time()

    print(
        f"      [{datetime.now().strftime('%H:%M:%S')}] [Cascade] "
        f"Stage 1: Extracting meanings for '{word}'..."
    )
    stage1_system = CASCADE_STAGE1_SYSTEM
    if salt:
        stage1_system += f"\n\nBenchmark Salt: {salt}"

    base_data = await _run_stage(
        "stage1_extraction",
        prompt=f"Identify all distinct meanings of the Finnish word '{word}'.",
        system_instruction=stage1_system,
        response_schema=STAGE1_SCHEMA,
        temperature=0.2,
        thinking_level="LOW",
        timeout=timeout,
        metrics=metrics,
    )

    async def process_meaning(meaning: dict, idx: int):
        definition = meaning["englishDefinition"]
        print(
            f"      [{datetime.now().strftime('%H:%M:%S')}] [Cascade] "
            f"Stage 2: CEFR examples for meaning {idx + 1}..."
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
            response_schema=STAGE2_SCHEMA,
            temperature=0.7,
            thinking_level="LOW",
            timeout=timeout,
            metrics=metrics,
        )

        print(
            f"      [{datetime.now().strftime('%H:%M:%S')}] [Cascade] "
            f"Stage 3: SpokenFi transform for meaning {idx + 1}..."
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
                response_schema=STAGE3_SCHEMA,
                temperature=0.0,
                thinking_level="MINIMAL",
                timeout=stage3_timeout,
                metrics=metrics,
            )
            spoken_map = build_spoken_map(spoken_data["spoken_examples"])
        except Exception as exc:
            print(
                f"      [{datetime.now().strftime('%H:%M:%S')}] [Cascade] "
                f"Stage 3 fallback for meaning {idx + 1}: "
                f"{str(exc) or type(exc).__name__}"
            )
            spoken_map = {}

        examples = assemble_examples(cefr_data["examples"], spoken_map)

        return {
            "englishDefinition": definition,
            "examples": examples,
            "synonyms": meaning["synonyms"],
            "antonyms": meaning["antonyms"],
            "definiendum": {"en": meaning["definiendum"]},
        }

    # return_exceptions=True: el fallo de una acepcion NO debe cancelar a las
    # corrutinas hermanas en vuelo ni tirar toda la palabra (H5). Cada resultado
    # se inspecciona por separado; las acepciones que fallaron se descartan del
    # entry final (Stage 2 no tiene fallback util) y se loguean.
    results = await asyncio.gather(
        *(process_meaning(meaning, idx) for idx, meaning in enumerate(base_data["meanings"])),
        return_exceptions=True,
    )

    final_entry = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            print(
                f"      [{datetime.now().strftime('%H:%M:%S')}] [Cascade] "
                f"Meaning {idx + 1} failed, skipped: "
                f"{str(result) or type(result).__name__}"
            )
            continue
        final_entry.append(result)

    summary = metrics.summary()
    summary["e2e_duration"] = time.time() - e2e_start
    summary["mode"] = "cascade"
    summary["model"] = FLASH_MODEL
    return final_entry, summary


if __name__ == "__main__":
    import sys

    word = sys.argv[1] if len(sys.argv) > 1 else "hana"
    result, metrics = asyncio.run(run_cascade(word))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
