# GDE Submission Draft

Hi everyone,

I benchmarked several mitigation strategies for the reported Gemini Flash latency spike on a Finnish dictionary-generation task.
This draft is generated from the current validated benchmark snapshot, so the numbers below only count outputs that passed structural quality checks.

## Snapshot

- Fastest partial-output strategy: Lazy Optimized (A1-B1) at 10.84s average latency.
- API-level schema enforcement changed end-to-end latency by -8.9% versus the monolithic baseline.

## Suggested message

The strongest pattern in my benchmark is that output-contract pressure matters almost as much as reasoning depth.
Prompt variants that keep JSON MIME enforcement but avoid a rigid response schema tend to complete faster, and a quality gate is essential because some fast runs still produce unusable dictionaries.
For production I would recommend: optimized prompt first, explicit thinking budget as a kill switch, output validation, and a fallback path for the cases where Flash still drifts.

All generated artifacts for this run are available in `benchmark_results/`.
