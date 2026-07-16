"""Regenera la fixture de replay desde los datasets reales versionados.

Fuentes (ambas corridas REALES contra la API de Gemini, versionadas en el
repo): ``benchmark_results/salvaged_results.json`` (n=120) y
``benchmark_results/benchmark_data_extension.json`` (n=120). De cada corrida
valida se toma su duracion end-to-end; el resultado es la distribucion de
latencias que el ``ReplayProvider`` reproduce a escala.

Para las estrategias multi-etapa (cascade/pipeline) los datasets no guardan
el desglose por stage, asi que la fixture declara un reparto SINTETICO
(``stage_split``) de la duracion real de cada corrida entre sus stages. Eso
preserva la duracion e2e real y la estructura de llamadas (1 + 2M), que es lo
que el replay puede gatear honestamente; el reparto interno es una convencion
documentada, no una medicion.

Uso (desde la raiz del repo):
    python -m benchmarks.generate_fixture
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES = (
    "benchmark_results/salvaged_results.json",
    "benchmark_results/benchmark_data_extension.json",
)
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "replay_v1.json"

FULL_LEVELS = ("a1", "a2", "b1", "b2", "c1", "c2")
LAZY_LEVELS = ("a1", "a2", "b1")
NUM_MEANINGS = 3

STRATEGY_KINDS = {
    "monolithic": ("single_stream", "full"),
    "monolithic_schema": ("single_sync", "full"),
    "optimized_monolithic": ("single_stream", "full"),
    "lazy_optimized": ("single_stream", "lazy"),
    "thinking_budget": ("single_stream", "full"),
    "pro_model": ("single_stream", "full"),
    "cascade": ("multistage_parallel", "full"),
    "pipeline": ("multistage_sequential", "full"),
}

# Reparto sintetico de la duracion e2e real entre stages (ver docstring).
# cascade corre las M ramas stage2->stage3 en paralelo: e2e = s1 + (s2 + s3).
# pipeline las corre en secuencia: e2e = s1 + M * (s2 + s3).
STAGE_SPLITS = {
    "cascade": {"stage1": 0.25, "stage2": 0.45, "stage3": 0.30},
    "pipeline": {"stage1": 0.10, "stage2_fraction_of_rest": 2 / 3},
}


def _entry(levels, spoken):
    return [
        {
            "englishDefinition": "a tap or faucet (replay fixture, not a model output)",
            "definiendum": {"en": "tap"},
            "synonyms": [],
            "antonyms": [],
            "examples": [
                {
                    "sourceFi": f"Esimerkki {level}.",
                    "spokenFi": f"Puhe {level}." if spoken else None,
                    "level": level,
                }
                for level in levels
            ],
        }
    ]


def _canned_payloads():
    return {
        "full_entry": _entry(FULL_LEVELS, spoken=True),
        "lazy_entry": _entry(LAZY_LEVELS, spoken=False),
        "stage1": {
            "meanings": [
                {
                    "englishDefinition": f"replay meaning #{index}",
                    "definiendum": "tap",
                    "synonyms": [],
                    "antonyms": [],
                }
                for index in range(NUM_MEANINGS)
            ]
        },
        "stage2": {
            "examples": [
                {"sourceFi": f"Esimerkki {level}.", "level": level} for level in FULL_LEVELS
            ]
        },
        "stage3": {
            "spoken_examples": [
                {"spokenFi": f"Puhe {level}.", "level": level} for level in FULL_LEVELS
            ]
        },
    }


def _collect_runs():
    per_strategy = {key: [] for key in STRATEGY_KINDS}
    used_sources = []
    for relative in SOURCES:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        used_sources.append(relative)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        for run in data.get("raw_runs", []):
            key = run.get("strategy")
            if key in per_strategy and run.get("success"):
                per_strategy[key].append(run)
    if not used_sources:
        raise SystemExit(f"Ninguna fuente encontrada: {SOURCES}")
    return per_strategy, used_sources


def _usage_from_runs(runs):
    """Usage promedio por estrategia. El split prompt/candidates solo existe en
    la corrida de extension; cuando falta se aproxima (mismo criterio heuristico
    que scripts/salvage.py, documentado como aproximacion)."""
    totals = [run.get("total_tokens", 0) for run in runs]
    thoughts = [run.get("thought_tokens", 0) for run in runs]
    prompts = [run["prompt_tokens"] for run in runs if run.get("prompt_tokens")]
    avg_total = round(sum(totals) / len(totals)) if totals else 0
    avg_thought = round(sum(thoughts) / len(thoughts)) if thoughts else 0
    if prompts:
        avg_prompt = round(sum(prompts) / len(prompts))
    else:
        avg_prompt = max(avg_total - avg_thought - 800, round(avg_total * 0.7))
    avg_candidates = max(avg_total - avg_thought - avg_prompt, 0)
    return {
        "prompt_token_count": avg_prompt,
        "candidates_token_count": avg_candidates,
        "thoughts_token_count": avg_thought,
        "total_token_count": avg_total,
    }


def main():
    per_strategy, used_sources = _collect_runs()

    strategies = {}
    for key, (kind, levels) in STRATEGY_KINDS.items():
        runs = per_strategy[key]
        if not runs:
            raise SystemExit(f"Sin corridas validas para '{key}' en {used_sources}")
        # Orden cronologico de origen (NO ordenado): el replay cicla
        # durations_s[i % n], asi que un subconjunto de N iteraciones debe ser
        # una muestra representativa, no "las N corridas mas rapidas".
        durations = [round(float(run["duration"]), 2) for run in runs]
        strategies[key] = {
            "kind": kind,
            "levels": levels,
            "durations_s": durations,
            "usage": _usage_from_runs(runs),
        }
        if key in STAGE_SPLITS:
            strategies[key]["stage_split"] = STAGE_SPLITS[key]

    fixture = {
        "fixture_version": 1,
        "sources": used_sources,
        "provenance": (
            "Duraciones e2e de corridas reales contra la API de Gemini "
            "(modelos gemini-3-flash-preview / gemini-3.1-pro-preview, "
            "timeout 180s). El stage_split de cascade/pipeline es un reparto "
            "sintetico documentado, no una medicion por stage."
        ),
        # 0.05: con escalas menores el overhead del event loop (granularidad
        # del timer en Windows ~15ms por sleep) distorsiona las estrategias de
        # e2e chico (cascade), y el gate relativo pierde señal.
        "time_scale": 0.05,
        "num_meanings": NUM_MEANINGS,
        "payloads": _canned_payloads(),
        "strategies": strategies,
    }

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FIXTURE_PATH, "w", encoding="utf-8") as handle:
        json.dump(fixture, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    counts = {key: len(value["durations_s"]) for key, value in strategies.items()}
    print(f"Fixture escrita en {FIXTURE_PATH}")
    print(f"Corridas validas por estrategia: {counts}")


if __name__ == "__main__":
    main()
