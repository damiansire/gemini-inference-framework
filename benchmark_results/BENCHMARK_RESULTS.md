# Gemini Latency Benchmark Report

Generated: 2026-04-10 16:33:40
Words: hana, kuusi, juosta, vanha, silta
Iterations per strategy: 3
Timeout per call: 180s
Models benchmarked: gemini-3-flash-preview, gemini-3.1-pro-preview

## Executive Summary

| Metric | Monolithic (No Schema) | Monolithic (Strict Schema) | Optimized Monolithic | Lazy Optimized (A1-B1) | Pipeline (Multi-stage) | Structured Cascade | Thinking Budget (LOW) | Pro Model |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Avg Latency (E2E)** | 21.98s | 28.88s | 20.70s | 16.14s | 152.89s | 17.23s | 8.21s | 54.67s |
| **Time to 1st Token (TTFT)** | 15.70s | 0.00s | 14.46s | 13.37s | 0.00s | 0.00s | 2.12s | 42.17s |
| **Avg Thought Tokens** | 2,648 | 4,049 | 2,645 | 2,586 | 10,713 | 3,862 | 0 | 4,822 |
| **Avg Total Tokens** | 7,704 | 8,950 | 4,609 | 3,913 | 13,983 | 8,704 | 4,876 | 10,338 |
| **Avg Cost per Request (est.)** | $0.00180 | $0.00235 | $0.00149 | $0.00141 | $0.00485 | $0.00227 | $0.00073 | $0.03400 |
| **API Success Rate** | 100% | 100% | 80% | 100% | 93% | 100% | 100% | 93% |
| **Valid Output Rate** | 100% | 100% | 73% | 100% | 93% | 100% | 93% | 87% |

## Quality Gate

All leaderboard metrics above are calculated only from runs whose recorded `output_valid` flag is true.
In a live benchmark that flag comes from the output validator; this report was regenerated from logs via `salvage.py`, so the flag is read back from each run's logged value (the validator is not re-executed).
The validator checks JSON parseability, root shape, required keys, CEFR level coverage, and a headword policy that rejects obvious grammatical-form collisions.

Cost is an estimate, not a billed figure: it multiplies token counts by the model's published per-million rates.
When a report is regenerated from logs, the input/output token split is not in the log and is approximated by a heuristic in `salvage.py`, so the cost column here is doubly estimated.

## Strategy Notes

- Lazy Optimized is the fastest partial-output strategy at 16.14s average latency.
- The fastest fully valid strategy is Lazy Optimized (A1-B1) at 16.14s average latency.
- Outside the lazy variant, the lowest-latency approach is Thinking Budget (LOW).
- Schema enforcement changed average thought-token usage by +52.9% versus the monolithic baseline.

## Failure Breakdown

- Monolithic (No Schema): 15/15 valid runs, 0 validation failures, 0 API failures.
- Monolithic (Strict Schema): 15/15 valid runs, 0 validation failures, 0 API failures.
- Optimized Monolithic: 11/15 valid runs, 1 validation failures, 3 API failures.
- Lazy Optimized (A1-B1): 15/15 valid runs, 0 validation failures, 0 API failures.
- Pipeline (Multi-stage): 14/15 valid runs, 0 validation failures, 1 API failures.
- Structured Cascade: 15/15 valid runs, 0 validation failures, 0 API failures.
- Thinking Budget (LOW): 14/15 valid runs, 1 validation failures, 0 API failures.
- Pro Model: 13/15 valid runs, 1 validation failures, 1 API failures.
