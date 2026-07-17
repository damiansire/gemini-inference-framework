import json
import re

from scripts.compare_benchmarks import STRATEGIES, _generate_benchmark_report, summarize_metrics

# regex to match each block:
# [1/120] Strategy Name | word='word' | iteration=X | salt=YYY
#   VALID | dur=XX.XXs | ttft=XX.XXs | thought=XX,XXX | total=XX,XXX |
#   api_success=True | output_valid=True

_BLOCK_PATTERN = re.compile(
    r"\[\d+/\d+\]\s+(.*?)\s+\|\s+word='([^']+)'\s+\|\s+iteration=(\d+)\s+\|"
    r"\s+salt=([a-f0-9]+).*?(VALID|FAILED|TIMEOUT)\s+\|\s+dur=([0-9.]+)s\s+\|"
    r"\s+ttft=([0-9.]+s|N/A)\s+\|\s+thought=([\d,]+)\s+\|\s+total=([\d,]+)\s+\|"
    r"\s+api_success=(True|False)\s+\|\s+output_valid=(True|False)",
    re.DOTALL,
)

_STRATEGIES_MAP = {
    "Monolithic (No Schema)": "monolithic",
    "Monolithic (Strict Schema)": "monolithic_schema",
    "Optimized Monolithic": "optimized_monolithic",
    "Lazy Optimized (A1-B1)": "lazy_optimized",
    "Pipeline (Multi-stage)": "pipeline",
    "Structured Cascade": "cascade",
    "Thinking Budget (LOW)": "thinking_budget",
    "Pro Model": "pro_model",
}


def parse_run_records(content):
    """Reconstruye los run records desde un log de consola del benchmark.

    Preserva la clasificacion del run tal como la imprimio el orquestador:
    ``success`` (VALID), ``timed_out`` (TIMEOUT) y los flags api_success/
    output_valid. ``summarize_metrics`` consume ``timed_out`` para la fila
    ``timeout_runs``: degradar un TIMEOUT a error generico aca subreportaria
    los timeouts en el reporte regenerado.
    """
    records = []
    for match in _BLOCK_PATTERN.finditer(content):
        (
            strat_display,
            word,
            it,
            salt,
            status,
            dur,
            ttft_str,
            thought_str,
            total_str,
            api_s,
            output_v,
        ) = match.groups()
        strat_key = _STRATEGIES_MAP.get(strat_display.strip(), strat_display.strip())

        ttft_val = None if ttft_str == "N/A" else float(ttft_str.replace("s", ""))

        tot = int(total_str.replace(",", ""))
        tho = int(thought_str.replace(",", ""))

        # ESTIMATED cost only: the log records total + thought tokens but not the
        # input/output split, so the split below is a heuristic, NOT a measurement.
        # Thinking tokens are billed as output; we assume ~800 standard output
        # tokens on top, falling back to 30% of total when that overshoots.
        # The generated report labels this column as estimated and documents the
        # heuristic in its Quality Gate section. Regenerate from a real run if you
        # need a measured split.
        est_out = tho + 800
        if est_out > tot:
            est_out = tot * 0.3  # Fallback safely
        est_in = tot - est_out

        if strat_key == "pro_model":
            cost_val = (est_in / 1000000.0 * 1.25) + (est_out / 1000000.0 * 5.00)
        else:
            cost_val = (est_in / 1000000.0 * 0.10) + (est_out / 1000000.0 * 0.40)

        records.append(
            {
                "strategy": strat_key,
                "strategy_name": strat_display.strip(),
                "word": word,
                "iteration": int(it),
                "salt": salt,
                "duration": float(dur),
                "ttft": ttft_val,
                "thought_tokens": tho,
                "total_tokens": tot,
                "api_success": api_s == "True",
                "output_valid": output_v == "True",
                "success": status == "VALID",
                "timed_out": status == "TIMEOUT",
                "cost": cost_val,
            }
        )
    return records


def salvage():
    with open("benchmark_live.log") as f:
        content = f.read()

    results_metadata = {
        "metadata": {
            "words": ["hana", "kuusi", "juosta", "vanha", "silta"],
            "strategies": [
                "monolithic",
                "monolithic_schema",
                "optimized_monolithic",
                "lazy_optimized",
                "pipeline",
                "cascade",
                "thinking_budget",
                "pro_model",
            ],
            "iterations": 3,
            "timeout": 180,
        },
        "raw_runs": [],
        "summaries": {},
    }

    strategy_results = {s: [] for s in results_metadata["metadata"]["strategies"]}

    records = parse_run_records(content)
    for run_record in records:
        results_metadata["raw_runs"].append(run_record)
        if run_record["strategy"] in strategy_results:
            strategy_results[run_record["strategy"]].append(run_record)

    if not records:
        print(
            "WARNING: 0 run blocks matched in benchmark_live.log; "
            "the generated summaries will be empty. Check that the log format "
            "matches the expected '[N/M] Strategy | word=... | ...' pattern."
        )

    for key in results_metadata["metadata"]["strategies"]:
        if strategy_results.get(key):
            summary = summarize_metrics(strategy_results[key])
            results_metadata["summaries"][key] = {
                "name": STRATEGIES[key]["name"],
                "description": STRATEGIES.get(key, {}).get("description", ""),
                **summary,
            }

    with open("benchmark_results/salvaged_results.json", "w", encoding="utf-8") as handle:
        json.dump(results_metadata, handle, indent=2, ensure_ascii=False, default=str)

    _generate_benchmark_report(results_metadata)
    print("SALVAGE SUCCESSFUL: Reports generated from log file.")


if __name__ == "__main__":
    salvage()
