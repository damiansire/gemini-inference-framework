"""
Gemini latency benchmark suite with output validation.

The benchmark only counts runs as successful when the API call completes and
the returned dictionary structure is usable for downstream consumers.
"""

import argparse
import asyncio
import json
import os
import random
import statistics
import time
import traceback
import uuid
from datetime import datetime

from dotenv import load_dotenv

from prompts import TEST_WORDS
from strategies.cascade.runner import run_cascade as run_cascade_strategy_base
from strategies.lazy_optimized.runner import run_lazy_optimized
from strategies.monolithic.runner import run_monolithic, run_monolithic_schema
from strategies.optimized_monolithic.runner import run_optimized
from strategies.output_validation import FULL_LEVELS, LAZY_LEVELS, validate_dictionary_output
from strategies.pipeline.runner import run_pipeline as run_pipeline_strategy_base
from strategies.pro_model.runner import run_pro_model
from strategies.thinking_budget.runner import run_thinking_budget
from strategies.utils import FLASH_MODEL, PRO_MODEL, _create_client, estimate_cost

load_dotenv()

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(ROOT_DIR, "benchmark_results")


async def run_pipeline_strategy(word, salt=None, timeout=180):
    """Sequential multi-stage baseline."""
    try:
        result, metrics = await run_pipeline_strategy_base(word, salt=salt, timeout=timeout)
        duration = metrics.get("e2e_duration", 0)
        return {
            "success": True,
            "duration": duration,
            "ttft": metrics.get("ttft", 0),
            "prompt_tokens": metrics["prompt_tokens"],
            "candidate_tokens": metrics["candidate_tokens"],
            "thought_tokens": metrics["thought_tokens_est"],
            "total_tokens": metrics["total_tokens"],
            "cost": estimate_cost(
                metrics["prompt_tokens"],
                metrics["candidate_tokens"] + metrics["thought_tokens_est"],
                FLASH_MODEL,
            ),
            "timed_out": False,
            "text_output": result,
        }
    except Exception as exc:
        return {
            "success": False,
            "duration": 0,
            "ttft": 0,
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "thought_tokens": 0,
            "total_tokens": 0,
            "cost": 0,
            "timed_out": isinstance(exc, asyncio.TimeoutError),
            "error": str(exc) or type(exc).__name__,
        }


async def run_cascade_strategy(word, salt=None, timeout=180):
    """Structured cascade with explicit thinking controls."""
    try:
        result, metrics = await run_cascade_strategy_base(word, salt=salt, timeout=timeout)
        duration = metrics.get("e2e_duration", 0)
        return {
            "success": True,
            "duration": duration,
            "ttft": metrics.get("ttft", 0),
            "prompt_tokens": metrics["prompt_tokens"],
            "candidate_tokens": metrics["candidate_tokens"],
            "thought_tokens": metrics["thought_tokens_est"],
            "total_tokens": metrics["total_tokens"],
            "cost": estimate_cost(
                metrics["prompt_tokens"],
                metrics["candidate_tokens"] + metrics["thought_tokens_est"],
                FLASH_MODEL,
            ),
            "timed_out": False,
            "text_output": result,
        }
    except Exception as exc:
        return {
            "success": False,
            "duration": 0,
            "ttft": 0,
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "thought_tokens": 0,
            "total_tokens": 0,
            "cost": 0,
            "timed_out": isinstance(exc, asyncio.TimeoutError),
            "error": str(exc) or type(exc).__name__,
        }


STRATEGIES = {
    "monolithic": {
        "name": "Monolithic (No Schema)",
        "runner": run_monolithic,
        "description": "Single-shot prompt with JSON MIME enforcement but no response schema",
        "expected_levels": FULL_LEVELS,
    },
    "monolithic_schema": {
        "name": "Monolithic (Strict Schema)",
        "runner": run_monolithic_schema,
        "description": "Single-shot prompt with API-level response schema enforcement",
        "expected_levels": FULL_LEVELS,
    },
    "pipeline": {
        "name": "Pipeline (Multi-stage)",
        "runner": run_pipeline_strategy,
        "description": (
            "Sequential decomposition into extraction, CEFR generation, "
            "and SpokenFi transformation"
        ),
        "expected_levels": FULL_LEVELS,
    },
    "thinking_budget": {
        "name": "Thinking Budget (LOW)",
        "runner": run_thinking_budget,
        "description": "Monolithic baseline with thinking_level=LOW as a thinking cap",
        "expected_levels": FULL_LEVELS,
    },
    "pro_model": {
        "name": "Pro Model",
        "runner": run_pro_model,
        "description": "Same task on Gemini Pro for cost and stability comparison",
        "expected_levels": FULL_LEVELS,
    },
    "cascade": {
        "name": "Structured Cascade",
        "runner": run_cascade_strategy,
        "description": "Parallelized multi-stage approach with per-stage thinking controls",
        "expected_levels": FULL_LEVELS,
    },
    "optimized_monolithic": {
        "name": "Optimized Monolithic",
        "runner": run_optimized,
        "description": "Shorter, pattern-driven system prompt with JSON MIME enforcement",
        "expected_levels": FULL_LEVELS,
    },
    "lazy_optimized": {
        "name": "Lazy Optimized (A1-B1)",
        "runner": run_lazy_optimized,
        "description": "Optimized prompt that deliberately returns only A1, A2, and B1 examples",
        "expected_levels": LAZY_LEVELS,
    },
}


def summarize_metrics(runs):
    successful = [run for run in runs if run["success"]]
    api_successful = [run for run in runs if run.get("api_success")]
    validation_failed = [
        run for run in runs if run.get("api_success") and not run.get("output_valid")
    ]
    timed_out = [run for run in runs if run.get("timed_out", False)]

    if not successful:
        return {
            "avg_duration": 0,
            "min_duration": 0,
            "max_duration": 0,
            "std_duration": 0,
            "avg_ttft": None,
            "std_ttft": 0,
            "avg_total_tokens": 0,
            "avg_thought_tokens": 0,
            "max_thought_tokens": 0,
            "avg_cost": 0,
            "total_runs": len(runs),
            "successful_runs": 0,
            "api_successful_runs": len(api_successful),
            "failed_runs": len(runs),
            "validation_failed_runs": len(validation_failed),
            "timeout_runs": len(timed_out),
            "failure_rate": 1.0 if runs else 0,
            "api_success_rate": len(api_successful) / len(runs) if runs else 0,
            "valid_output_rate": 0,
        }

    durations = [run["duration"] for run in successful]
    valid_ttfts = [run["ttft"] for run in successful if run.get("ttft") is not None]
    total_tokens = [run["total_tokens"] for run in successful]
    thought_tokens = [run["thought_tokens"] for run in successful]
    costs = [run["cost"] for run in successful]

    return {
        "avg_duration": statistics.mean(durations),
        "min_duration": min(durations),
        "max_duration": max(durations),
        "std_duration": statistics.stdev(durations) if len(durations) > 1 else 0,
        "avg_ttft": statistics.mean(valid_ttfts) if valid_ttfts else None,
        "std_ttft": statistics.stdev(valid_ttfts) if len(valid_ttfts) > 1 else 0,
        "avg_total_tokens": statistics.mean(total_tokens),
        "avg_thought_tokens": statistics.mean(thought_tokens),
        "max_thought_tokens": max(thought_tokens),
        "avg_cost": statistics.mean(costs),
        "total_runs": len(runs),
        "successful_runs": len(successful),
        "api_successful_runs": len(api_successful),
        "failed_runs": len(runs) - len(successful),
        "validation_failed_runs": len(validation_failed),
        "timeout_runs": len(timed_out),
        "failure_rate": (len(runs) - len(successful)) / len(runs) if runs else 0,
        "api_success_rate": len(api_successful) / len(runs) if runs else 0,
        "valid_output_rate": len(successful) / len(runs) if runs else 0,
    }


def _normalize_result(strategy_key, result):
    normalized = {
        "success": bool(result.get("success")),
        "duration": result.get("duration", 0),
        "ttft": result.get("ttft", 0),
        "prompt_tokens": result.get("prompt_tokens", 0),
        "candidate_tokens": result.get("candidate_tokens", 0),
        "thought_tokens": result.get("thought_tokens", 0),
        "total_tokens": result.get("total_tokens", 0),
        "cost": result.get("cost", 0),
        "timed_out": result.get("timed_out", False),
        "error": result.get("error"),
        "text_output": result.get("text_output"),
    }

    for key, value in result.items():
        if key not in normalized:
            normalized[key] = value

    normalized["api_success"] = normalized["success"]
    normalized["output_valid"] = False
    normalized["validation_errors"] = []

    if not normalized["api_success"]:
        return normalized

    validation = validate_dictionary_output(
        normalized.get("text_output"),
        expected_levels=STRATEGIES[strategy_key]["expected_levels"],
    )
    normalized["validation_errors"] = validation["errors"]
    normalized["output_valid"] = validation["ok"]

    original_output = normalized.get("text_output")
    if validation["normalized"] is not None:
        if isinstance(original_output, str):
            normalized["raw_text_output"] = original_output
        normalized["text_output"] = validation["normalized"]

    if not validation["ok"]:
        normalized["success"] = False
        details = "; ".join(validation["errors"][:3])
        normalized["error"] = f"Output validation failed: {details}"

    return normalized


async def warmup():
    """Warm the API to reduce first-request bias."""
    client = _create_client()
    try:
        await asyncio.to_thread(
            client.models.generate_content,
            model=FLASH_MODEL,
            contents="Say 'System Ready' if you are awake.",
        )
    except Exception as exc:
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] Warmup failed ({exc}), continuing anyway..."
        )


def _pick_fastest(summaries, exclude=None):
    exclude = set(exclude or [])
    candidates = [
        (key, value)
        for key, value in summaries.items()
        if key not in exclude and value["successful_runs"] > 0
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[1]["avg_duration"])


def _pick_best_quality_speed(summaries):
    candidates = [
        (key, value)
        for key, value in summaries.items()
        if value["successful_runs"] > 0 and value["valid_output_rate"] >= 1.0
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[1]["avg_duration"])


def _write_report(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _generate_benchmark_report(data):
    summaries = data["summaries"]
    strategy_keys = list(summaries.keys())

    header = "| Metric |" + "".join(
        f" {summaries[key]['name']} |" for key in strategy_keys
    )
    divider = "| :--- |" + "".join(" :--- |" for _ in strategy_keys)

    rows = []
    metric_rows = [
        ("Avg Latency (E2E)", "avg_duration", lambda value: f"{value:.2f}s"),
        ("Latency Std Dev", "std_duration", lambda value: f"+/-{value:.2f}s"),
        (
            "Time to 1st Token (TTFT)",
            "avg_ttft",
            lambda value: "N/A" if not value else f"{value:.2f}s",
        ),
        ("Avg Thought Tokens", "avg_thought_tokens", lambda value: f"{value:,.0f}"),
        ("Avg Total Tokens", "avg_total_tokens", lambda value: f"{value:,.0f}"),
        ("Avg Cost per Request (est.)", "avg_cost", lambda value: f"${value:.5f}"),
        ("API Success Rate", "api_success_rate", lambda value: f"{value * 100:.0f}%"),
        ("Valid Output Rate", "valid_output_rate", lambda value: f"{value * 100:.0f}%"),
    ]
    for label, key, formatter in metric_rows:
        row = f"| **{label}** |"
        for strategy_key in strategy_keys:
            row += f" {formatter(summaries[strategy_key][key])} |"
        rows.append(row)

    report = [
        "# Gemini Latency Benchmark Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Words: {', '.join(data['metadata']['words'])}",
        f"Iterations per strategy: {data['metadata']['iterations']}",
        f"Timeout per call: {data['metadata']['timeout']}s",
        f"Models benchmarked: {FLASH_MODEL}, {PRO_MODEL}",
        "",
        "## Executive Summary",
        "",
        header,
        divider,
        *rows,
        "",
        "## Quality Gate",
        "",
        "All leaderboard metrics above are calculated only from runs whose "
        "recorded `output_valid` flag is true.",
        "In a live benchmark that flag comes from the output validator; in "
        "reports regenerated from logs via `salvage.py` it is read back from "
        "each run's logged flag (the validator is not re-executed).",
        "The validator checks JSON parseability, root shape, required keys, "
        "CEFR level coverage, and a headword policy that rejects obvious "
        "grammatical-form collisions.",
        "",
        "Cost is an estimate, not a billed figure: it multiplies token counts "
        "by the model's published per-million rates.",
        "When a report is regenerated from logs, the input/output token split "
        "is not in the log and is approximated by a heuristic in `salvage.py`, "
        "so the cost column there is doubly estimated.",
        "",
        "## Strategy Notes",
        "",
    ]

    fastest = _pick_fastest(summaries, exclude={"lazy_optimized"})
    best_quality = _pick_best_quality_speed(summaries)
    fastest_lazy = summaries.get("lazy_optimized")

    if fastest_lazy and fastest_lazy["successful_runs"] > 0:
        report.append(
            f"- Lazy Optimized is the fastest partial-output strategy at "
            f"{fastest_lazy['avg_duration']:.2f}s average latency."
        )
    if best_quality:
        report.append(
            f"- The fastest fully valid strategy is {best_quality[1]['name']} at "
            f"{best_quality[1]['avg_duration']:.2f}s average latency "
            f"(+/-{best_quality[1]['std_duration']:.2f}s)."
        )
        report.append(
            "- Latency is averaged over a small n per strategy with wide "
            "LLM-side variance; treat sub-second gaps between the top "
            "strategies as within the margin, not a clear winner."
        )
    if fastest:
        report.append(
            f"- Outside the lazy variant, the lowest-latency approach is {fastest[1]['name']}."
        )
    if summaries.get("monolithic_schema") and summaries.get("monolithic"):
        schema = summaries["monolithic_schema"]
        baseline = summaries["monolithic"]
        if baseline["avg_thought_tokens"] > 0:
            delta = ((schema["avg_thought_tokens"] / baseline["avg_thought_tokens"]) - 1) * 100
            report.append(
                f"- Schema enforcement changed average thought-token usage by "
            f"{delta:+.1f}% versus the monolithic baseline."
            )

    report.extend(
        [
            "",
            "## Failure Breakdown",
            "",
        ]
    )
    for strategy_key in strategy_keys:
        summary = summaries[strategy_key]
        report.append(
            f"- {summary['name']}: {summary['successful_runs']}/"
            f"{summary['total_runs']} valid runs, "
            f"{summary['validation_failed_runs']} validation failures, "
            f"{summary['total_runs'] - summary['api_successful_runs']} API failures."
        )

    report_path = os.path.join(RESULTS_DIR, "BENCHMARK_RESULTS.md")
    _write_report(report_path, "\n".join(report) + "\n")


def _generate_gde_submission(data):
    summaries = data["summaries"]
    best_full = _pick_best_quality_speed(summaries)
    lazy = summaries.get("lazy_optimized")

    lines = [
        "# GDE Submission Draft",
        "",
        "Hi everyone,",
        "",
        "I benchmarked several mitigation strategies for the reported Gemini "
        "Flash latency spike on a Finnish dictionary-generation task.",
        "This draft is generated from the current validated benchmark "
        "snapshot, so the numbers below only count outputs that passed "
        "structural quality checks.",
        "",
        "## Snapshot",
        "",
    ]

    if lazy and lazy["successful_runs"] > 0:
        lines.append(
            f"- Fastest partial-output strategy: Lazy Optimized (A1-B1) at "
            f"{lazy['avg_duration']:.2f}s average latency."
        )
    if best_full:
        lines.append(
            f"- Fastest fully valid strategy: {best_full[1]['name']} at "
            f"{best_full[1]['avg_duration']:.2f}s average latency."
        )
    if summaries.get("monolithic_schema") and summaries.get("monolithic"):
        schema = summaries["monolithic_schema"]
        baseline = summaries["monolithic"]
        if baseline["avg_duration"] > 0:
            latency_delta = ((schema["avg_duration"] / baseline["avg_duration"]) - 1) * 100
            lines.append(
                f"- API-level schema enforcement changed end-to-end latency by "
            f"{latency_delta:+.1f}% versus the monolithic baseline."
            )

    lines.extend(
        [
            "",
            "## Suggested message",
            "",
            "The strongest pattern in my benchmark is that output-contract "
            "pressure matters almost as much as reasoning depth.",
            "Prompt variants that keep JSON MIME enforcement but avoid a rigid "
            "response schema tend to complete faster, and a quality gate is "
            "essential because some fast runs still produce unusable "
            "dictionaries.",
            "For production I would recommend: optimized prompt first, explicit "
            "thinking budget as a kill switch, output validation, and a "
            "fallback path for the cases where Flash still drifts.",
            "",
            "All generated artifacts for this run are available in `benchmark_results/`.",
        ]
    )

    path = os.path.join(RESULTS_DIR, "GDE_SUBMISSION_DRAFT.md")
    _write_report(path, "\n".join(lines) + "\n")


def _generate_article_draft(data):
    summaries = data["summaries"]
    best_full = _pick_best_quality_speed(summaries)

    lines = [
        "# Agent Engineering Draft",
        "",
        "This draft is generated from the current validated benchmark snapshot.",
        "",
        "## Core point",
        "",
        "The benchmark suggests that the production problem is not just "
        "runaway reasoning.",
        "It is the interaction between lexical ambiguity, rigid output "
        "contracts, and missing downstream validation.",
        "",
        "## Current takeaways",
        "",
    ]

    if best_full:
        lines.append(
            f"- The current fastest fully valid strategy is "
            f"{best_full[1]['name']} at {best_full[1]['avg_duration']:.2f}s."
        )

    lines.extend(
        [
            "- A quality-adjusted benchmark is more honest than ranking raw "
            "latency over invalid outputs.",
            "- Multi-stage orchestration is only persuasive when the "
            "implementation is reproducible and each stage is independently "
            "validated.",
            "- Data-specific claims should live next to the benchmark snapshot "
            "that produced them.",
        ]
    )

    path = os.path.join(RESULTS_DIR, "ARTICLE_AGENT_ENGINEERING_DRAFT.md")
    _write_report(path, "\n".join(lines) + "\n")


async def main():
    parser = argparse.ArgumentParser(
        description="Gemini latency benchmark with output validation"
    )
    parser.add_argument("--words", nargs="+", default=TEST_WORDS, help="Words to benchmark")
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Iterations per strategy and word",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Timeout per API call in seconds",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=list(STRATEGIES.keys()),
        choices=list(STRATEGIES.keys()),
        help="Subset of strategies to benchmark",
    )
    parser.add_argument(
        "--output",
        default="benchmark_data.json",
        help="Filename to write inside benchmark_results/",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  GEMINI LATENCY BENCHMARK SUITE")
    print("  Latency, cost, and output validity")
    print("=" * 70)
    print(f"  Words: {args.words}")
    print(f"  Strategies: {args.strategies}")
    print(f"  Iterations: {args.iterations}")
    print(f"  Timeout: {args.timeout}s")
    print(
        f"  Total runs: {len(args.words) * len(args.strategies) * args.iterations} "
        "(multi-stage strategies emit several Gemini calls per run)"
    )
    print("=" * 70)

    os.makedirs(RESULTS_DIR, exist_ok=True)

    all_results = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "words": args.words,
            "iterations": args.iterations,
            "timeout": args.timeout,
            "strategies_tested": args.strategies,
            "models": {
                "flash": FLASH_MODEL,
                "pro": PRO_MODEL,
            },
            "quality_gate": {
                "headword_policy": True,
                "json_validation": True,
                "cefr_level_validation": True,
            },
        },
        "raw_runs": [],
        "summaries": {},
    }

    strategy_results = {key: [] for key in args.strategies}

    await warmup()

    tasks = []
    for word in args.words:
        for strategy_key in args.strategies:
            for iteration in range(1, args.iterations + 1):
                tasks.append((word, strategy_key, iteration))
    random.shuffle(tasks)

    for index, (word, strategy_key, iteration) in enumerate(tasks, start=1):
        strategy = STRATEGIES[strategy_key]
        salt = f"{uuid.uuid4().hex[:8]}-{int(time.time() * 1000)}"
        print(
            f"\n[{index}/{len(tasks)}] {strategy['name']} | word='{word}' | "
            f"iteration={iteration} | salt={salt[:8]}"
        )

        try:
            raw_result = await strategy["runner"](word, salt=salt, timeout=args.timeout)
        except Exception as exc:
            traceback.print_exc()
            raw_result = {
                "success": False,
                "duration": 0,
                "ttft": 0,
                "prompt_tokens": 0,
                "candidate_tokens": 0,
                "thought_tokens": 0,
                "total_tokens": 0,
                "cost": 0,
                "timed_out": False,
                "error": str(exc),
            }

        result = _normalize_result(strategy_key, raw_result)
        status = "VALID" if result["success"] else (
            "TIMEOUT" if result.get("timed_out") else "FAILED"
        )
        ttft_str = f"{result['ttft']:.2f}s" if result.get('ttft') is not None else "N/A"
        print(
            f"  {status} | dur={result['duration']:.2f}s | ttft={ttft_str} | "
            f"thought={result['thought_tokens']:,} | total={result['total_tokens']:,} | "
            f"api_success={result['api_success']} | output_valid={result['output_valid']}"
        )
        if result.get("error"):
            print(f"  error: {result['error']}")

        run_record = {
            "strategy": strategy_key,
            "strategy_name": strategy["name"],
            "word": word,
            "iteration": iteration,
            "salt": salt,
            **result,
        }
        all_results["raw_runs"].append(run_record)
        strategy_results[strategy_key].append(result)

    print(f"\n{'=' * 70}")
    print("  AGGREGATED RESULTS")
    print(f"{'=' * 70}")

    for strategy_key in args.strategies:
        summary = summarize_metrics(strategy_results[strategy_key])
        all_results["summaries"][strategy_key] = {
            "name": STRATEGIES[strategy_key]["name"],
            "description": STRATEGIES[strategy_key]["description"],
            **summary,
        }
        print(
            f"{STRATEGIES[strategy_key]['name']}: "
            f"valid {summary['successful_runs']}/{summary['total_runs']} | "
            f"api {summary['api_successful_runs']}/{summary['total_runs']} | "
            f"avg {summary['avg_duration']:.2f}s"
        )

    output_path = os.path.join(RESULTS_DIR, args.output)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(all_results, handle, indent=2, ensure_ascii=False, default=str)

    _generate_benchmark_report(all_results)
    _generate_gde_submission(all_results)
    _generate_article_draft(all_results)

    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
