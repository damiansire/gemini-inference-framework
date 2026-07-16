# Gemini Latency Benchmark Report

Generated: 2026-07-11 07:26:13
Words: kirja, syödä, iso, nopeasti, talossa
Iterations per strategy: 3
Timeout per call: 180s
Models benchmarked: gemini-3-flash-preview, gemini-3.1-pro-preview

## Executive Summary

| Metric | Monolithic (No Schema) | Monolithic (Strict Schema) | Pipeline (Multi-stage) | Thinking Budget (LOW) | Pro Model | Structured Cascade | Optimized Monolithic | Lazy Optimized (A1-B1) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Avg Latency (E2E)** | 24.67s | 22.47s | 139.51s | 7.02s | 35.23s | 12.32s | 22.29s | 10.84s |
| **Latency Std Dev** | +/-11.03s | +/-9.73s | +/-74.54s | +/-2.21s | +/-13.84s | +/-4.53s | +/-15.84s | +/-5.54s |
| **95% CI of Avg Latency** | [17.84s, 31.51s] | [16.11s, 28.83s] | [84.30s, 194.73s] | [5.65s, 8.39s] | [21.67s, 48.79s] | [9.36s, 15.28s] | [11.31s, 33.27s] | [5.99s, 15.70s] |
| **Time to 1st Token (TTFT)** | 19.39s | N/A | N/A | 1.41s | 26.71s | N/A | 18.97s | 9.07s |
| **Avg Thought Tokens** | 3,796 | 3,721 | 15,918 | 0 | 3,216 | 2,640 | 3,816 | 1,777 |
| **Avg Total Tokens** | 8,849 | 8,597 | 20,055 | 4,929 | 8,089 | 6,820 | 5,470 | 2,924 |
| **Avg Cost per Request (est.)** | $0.00248 | $0.00238 | $0.00723 | $0.00091 | $0.02717 | $0.00190 | $0.00200 | $0.00099 |
| **API Success Rate** | 73% | 67% | 53% | 80% | 53% | 60% | 53% | 33% |
| **Valid Output Rate** | 67% | 60% | 47% | 67% | 27% | 60% | 53% | 33% |

## Quality Gate

All leaderboard metrics above are calculated only from runs whose recorded `output_valid` flag is true.
In a live benchmark that flag comes from the output validator; in reports regenerated from logs via `salvage.py` it is read back from each run's logged flag (the validator is not re-executed).
The validator checks JSON parseability, root shape, required keys, CEFR level coverage, and a headword policy that rejects obvious grammatical-form collisions.

Cost is an estimate, not a billed figure: it multiplies token counts by the model's published per-million rates.
When a report is regenerated from logs, the input/output token split is not in the log and is approximated by a heuristic in `salvage.py`, so the cost column there is doubly estimated.

The 95% CI row uses a normal approximation (z=1.96), not a t-distribution: with the small per-strategy n typical here (a few iterations per word), the true t-critical value is wider, so treat this interval as an optimistic lower bound on uncertainty, not an exact one. See `confidence_interval_95` in compare_benchmarks.py.

## Strategy Notes

- Lazy Optimized is the fastest partial-output strategy at 10.84s average latency.
- Outside the lazy variant, the lowest-latency approach is Thinking Budget (LOW).
- Schema enforcement changed average thought-token usage by -2.0% versus the monolithic baseline.

## Failure Breakdown

- Monolithic (No Schema): 10/15 valid runs, 1 validation failures, 4 API failures.
- Monolithic (Strict Schema): 9/15 valid runs, 1 validation failures, 5 API failures.
- Pipeline (Multi-stage): 7/15 valid runs, 1 validation failures, 7 API failures.
- Thinking Budget (LOW): 10/15 valid runs, 2 validation failures, 3 API failures.
- Pro Model: 4/15 valid runs, 4 validation failures, 7 API failures.
- Structured Cascade: 9/15 valid runs, 0 validation failures, 6 API failures.
- Optimized Monolithic: 8/15 valid runs, 0 validation failures, 7 API failures.
- Lazy Optimized (A1-B1): 5/15 valid runs, 0 validation failures, 10 API failures.
