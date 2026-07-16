"""Combina el corpus original (n=120, salvaged_results.json) con la extension
real de gif-1 (n=120 nuevos, benchmark_data_extension.json) en un dataset
n=240 y regenera los reportes derivados con datos genuinamente reales de
ambas corridas.

No inventa numeros: ambos archivos de entrada son corridas reales contra la
API de Gemini (mismos modelos, mismo timeout=180s), en momentos distintos
(ver metadata.timestamp de cada mitad, preservada en run_record). Combinar dos
corridas reales del mismo metodo es honesto siempre que se documente asi -- lo
que este script hace en el reporte generado (nota de metodologia explicita).

Uso (una sola vez, desde la raiz del repo, despues de que
`python -m scripts.compare_benchmarks --output benchmark_data_extension.json`
haya terminado):
    python -m scripts.merge_extended_corpus
"""

import json
import os

from scripts.compare_benchmarks import (
    RESULTS_DIR,
    STRATEGIES,
    _generate_article_draft,
    _generate_benchmark_report,
    _generate_gde_submission,
    summarize_metrics,
)

ORIGINAL_PATH = os.path.join(RESULTS_DIR, "salvaged_results.json")
EXTENSION_PATH = os.path.join(RESULTS_DIR, "benchmark_data_extension.json")
MERGED_PATH = os.path.join(RESULTS_DIR, "benchmark_data_full_n240.json")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    original = _load(ORIGINAL_PATH)
    extension = _load(EXTENSION_PATH)

    original_runs = original["raw_runs"]
    extension_runs = extension["raw_runs"]
    combined_runs = original_runs + extension_runs

    if len(combined_runs) < 2 * len(original_runs):
        raise SystemExit(
            f"Esperaba al menos duplicar n={len(original_runs)}, "
            f"combinado da n={len(combined_runs)}. Abortando: no genero un "
            "reporte que afirme una muestra que no existe."
        )

    strategy_runs = {key: [] for key in STRATEGIES}
    for run in combined_runs:
        strategy_runs[run["strategy"]].append(run)

    summaries = {}
    for key, runs in strategy_runs.items():
        if not runs:
            continue
        summaries[key] = {
            "name": STRATEGIES[key]["name"],
            "description": STRATEGIES[key]["description"],
            **summarize_metrics(runs),
        }

    all_words = sorted(set(original["metadata"]["words"]) | set(extension["metadata"]["words"]))
    merged = {
        "metadata": {
            "note": (
                "Combina dos corridas reales independientes contra la API de "
                "Gemini (mismo timeout, mismos modelos): la original "
                f"({original['metadata'].get('timestamp', 'sin timestamp registrado')}) "
                f"y la extension gif-1 ({extension['metadata']['timestamp']}). "
                "n=240 (10 palabras x 3 iteraciones x 8 estrategias), el doble "
                "del n=120 original."
            ),
            "words": all_words,
            "iterations": original["metadata"]["iterations"],
            "timeout": original["metadata"]["timeout"],
            "strategies_tested": list(STRATEGIES.keys()),
            "original_timestamp": original["metadata"].get("timestamp"),
            "extension_timestamp": extension["metadata"]["timestamp"],
        },
        "raw_runs": combined_runs,
        "summaries": summaries,
    }

    with open(MERGED_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False, default=str)

    _generate_benchmark_report(merged)
    _generate_gde_submission(merged)
    _generate_article_draft(merged)

    print(f"Merged n={len(combined_runs)} runs -> {MERGED_PATH}")
    print("Regenerated BENCHMARK_RESULTS.md, GDE_SUBMISSION_DRAFT.md, ARTICLE_..._DRAFT.md")


if __name__ == "__main__":
    main()
