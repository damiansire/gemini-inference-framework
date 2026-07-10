"""Motor compartido de las estrategias multi-etapa (cascade/pipeline).

Antes cascade/runner.py y pipeline/runner.py tenian los 3 schemas
byte-identicos (solo el nombre de la variable cambiaba), ademas de
_parse_structured_response, _run_stage y el cuerpo de "extraer stage1 ->
generar CEFR -> transformar a puhekieli" duplicados. Si se corregia un schema
o el parseo en un lado, el otro quedaba con la version vieja sin que ningun
test lo notara -- justamente el escenario que invalida la comparacion que el
benchmark existe para hacer.

Las DOS diferencias reales entre las estrategias quedan parametrizadas por el
llamador, no duplicadas aca:
  - ejecucion paralela (cascade, via asyncio.gather) vs secuencial (pipeline).
  - thinking_level opcional por stage (cascade lo fija; pipeline no).

Hallazgo de /fragua evaluar 2026-07-10 (rank 4, veredicto REJECT).
"""

import json
from datetime import datetime

from google.genai import types

from prompts import CASCADE_STAGE1_SYSTEM, CASCADE_STAGE2_SYSTEM, CASCADE_STAGE3_SYSTEM

from .output_validation import parse_payload
from .stage_assembly import assemble_examples, build_spoken_map
from .utils import FLASH_MODEL, MetricsTracker, generate_content_sync

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


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _parse_structured_response(stage_name, response):
    if response["parsed"] is not None:
        return response["parsed"]
    data, errors = parse_payload(response["text"])
    if errors:
        raise ValueError(f"{stage_name}: {errors[0]}")
    return data


async def run_stage(
    stage_name: str,
    *,
    prompt: str,
    system_instruction: str,
    response_schema,
    temperature: float,
    timeout: float,
    metrics: MetricsTracker,
    thinking_level: str | None = None,
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


async def run_stage1_extraction(word, salt, timeout, metrics, *, label, thinking_level=None):
    print(f"      [{_ts()}] [{label}] Stage 1: Extracting meanings for '{word}'...")
    stage1_system = CASCADE_STAGE1_SYSTEM
    if salt:
        stage1_system += f"\n\nBenchmark Salt: {salt}"

    return await run_stage(
        "stage1_extraction",
        prompt=f"Identify all distinct meanings of the Finnish word '{word}'.",
        system_instruction=stage1_system,
        response_schema=STAGE1_SCHEMA,
        temperature=0.2,
        thinking_level=thinking_level,
        timeout=timeout,
        metrics=metrics,
    )


async def process_meaning(
    word,
    meaning: dict,
    idx: int,
    salt,
    timeout,
    metrics,
    *,
    label,
    thinking_level_stage2=None,
    thinking_level_stage3=None,
):
    """Stage 2 (CEFR examples) + Stage 3 (spoken Finnish, con fallback) para UNA acepcion."""
    definition = meaning["englishDefinition"]
    print(f"      [{_ts()}] [{label}] Stage 2: CEFR examples for meaning {idx}...")
    stage2_system = CASCADE_STAGE2_SYSTEM
    if salt:
        stage2_system += f"\n\nSalt: {salt}"

    cefr_data = await run_stage(
        f"stage2_cefr_m{idx}",
        prompt=(
            f"For the Finnish word '{word}' with this specific meaning: '{definition}', "
            "generate exactly 6 example sentences (A1-C2) in standard written Finnish."
        ),
        system_instruction=stage2_system,
        response_schema=STAGE2_SCHEMA,
        temperature=0.7,
        thinking_level=thinking_level_stage2,
        timeout=timeout,
        metrics=metrics,
    )

    print(f"      [{_ts()}] [{label}] Stage 3: SpokenFi transform for meaning {idx}...")
    stage3_system = CASCADE_STAGE3_SYSTEM
    if salt:
        stage3_system += f"\n\nSalt: {salt}"

    stage3_timeout = min(timeout, 45)
    try:
        spoken_data = await run_stage(
            f"stage3_spoken_m{idx}",
            prompt=(
                "Transform these standard Finnish sentences into spoken Finnish (puhekieli):\n"
                f"{json.dumps(cefr_data['examples'], ensure_ascii=False, indent=2)}"
            ),
            system_instruction=stage3_system,
            response_schema=STAGE3_SCHEMA,
            temperature=0.0,
            thinking_level=thinking_level_stage3,
            timeout=stage3_timeout,
            metrics=metrics,
        )
        spoken_map = build_spoken_map(spoken_data["spoken_examples"])
    except Exception as exc:
        print(
            f"      [{datetime.now().strftime('%H:%M:%S')}] [{label}] "
            f"Stage 3 fallback for meaning {idx}: {str(exc) or type(exc).__name__}"
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
