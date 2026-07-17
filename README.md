| Field      | Description |
|------------|------------|
| Disclaimer | This repository represents only my personal views and approach and has not been peer-reviewed; do not take it as absolute truth until the corresponding review is completed. |
| Status     | Pending peer review |


# gemini-inference-framework

Empirical benchmark and mitigation suite for the Gemini "reasoning explosion" on structured generation.

[![Dashboard deploy](https://github.com/damiansire/gemini-inference-framework/actions/workflows/deploy.yml/badge.svg)](https://github.com/damiansire/gemini-inference-framework/actions/workflows/deploy.yml)
[![Live dashboard](https://img.shields.io/badge/live-dashboard-blue)](https://damiansire.github.io/gemini-inference-framework/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Live benchmark dashboard:** <https://damiansire.github.io/gemini-inference-framework/>

> **TL;DR:**
> - **Community-reported value (not reproduced here):** a Finnish dictionary prompt was reported by a third party to make `gemini-3-flash-preview` consume **62k+ thought tokens** over **4 minutes 19 seconds**. Our n=120 benchmark never reproduced an explosion of that magnitude: our Monolithic (No Schema) baseline measured ~2,648 avg / 4,498 max thought tokens at 22.0s.
> - **Historical result (single manual n=120 run, pending CI-gated live verification):** across 120 runs (8 strategies x 5 words x 3 iterations, n=15 per strategy) the Monolithic baseline's average latency dropped from 22.0s to 17.2s using a **Structured Cascade** architecture (which rewrites the prompts into per-stage system messages rather than reusing the original prompt verbatim). The 95% CIs are wide and overlap ([19.8s, 24.2s] baseline vs [15.0s, 19.4s] Cascade); n=15 is far too small to advertise a reliability *rate*, so this README does not headline one (the run had 0 validation failures, but read the confidence intervals in the table, not a "100%" badge). These figures come from a one-off manual run against the live API; no CI job re-measures them yet. What CI does gate today: the selection logic that crowns the winner, the output quality gate, and (via the replay harness in `benchmarks/`) the relative latency profile of the strategy orchestration code.

---

## Context: The Problem

This project originated from a GenAI Circle discussion reporting extreme latency and token waste with `gemini-3-flash-preview`. The figures below are the **community-reported anecdote** that motivated the work — they are **not** one of our measurements and were **not reproduced** in our n=120 benchmark:

| Metric | Reported Value (third-party, not reproduced) |
|---|---|
| Duration | **4 minutes 19 seconds** |
| Input Tokens | ~3,400 |
| Output Tokens | ~1,069 |
| Thought Tokens | **62,910** |

> Our own worst-case measured thought usage was far smaller (see the n=120 leaderboard below: max 18,144 thought tokens on Pipeline, 4,498 on the Monolithic baseline). We document the gap rather than claim the reported explosion as our result.

The prompt generates structured JSON dictionary entries for Finnish words, requiring CEFR-leveled examples and phonological transformations to spoken Finnish (`spokenFi`). Our working hypothesis: the model enters **reasoning loops** due to competing constraints — strict JSON + creative generation + deterministic linguistic rules.

---

## Benchmark Results — single manual run (n=15 per strategy), not re-verified by CI, high variance

**8 strategies x 5 words x 3 iterations = 120 runs (n=15 per strategy)**, one manual pass against the live API, with UUID+epoch cache busting, randomized execution order, model warmup, and structural output validation. This is a **single manual run with wide LLM-side variance**, not a continuously re-measured guarantee: read the 95% confidence intervals, not just the point estimates. No CI job re-measures these absolute live-API numbers yet (the live workflow that regenerates this table is gated on an API-cost secret; see below). The table is **generated from the recorded run data**, not hand-typed:

<!-- BENCHMARK_TABLE:START -->
| Strategy | n (valid/total) | Avg Latency | 95% CI (latency) | Avg Thought | Max Thought | Avg Cost (USD, est.) | Success Rate | Failure Rate |
|---|---|---|---|---|---|---|---|---|
| Thinking Budget (LOW) | 14/15 | 8.2s | [7.1s, 9.3s] | 0 | 0 | $0.0007 | 93.3% | 6.7% |
| Lazy Optimized (A1-B1) | 15/15 | 16.1s | [11.8s, 20.5s] | 2,586 | 6,620 | $0.0014 | 100.0% | 0.0% |
| Structured Cascade | 15/15 | 17.2s | [15.0s, 19.4s] | 3,862 | 10,195 | $0.0023 | 100.0% | 0.0% |
| Optimized Monolithic | 11/15 | 20.7s | [16.0s, 25.4s] | 2,645 | 5,785 | $0.0015 | 73.3% | 26.7% |
| Monolithic (No Schema) | 15/15 | 22.0s | [19.8s, 24.2s] | 2,648 | 4,498 | $0.0018 | 100.0% | 0.0% |
| Monolithic (Strict Schema) | 15/15 | 28.9s | [25.2s, 32.6s] | 4,049 | 6,597 | $0.0023 | 100.0% | 0.0% |
| Pro Model | 13/15 | 54.7s | [48.9s, 60.4s] | 4,822 | 7,420 | $0.0340 | 86.7% | 13.3% |
| Pipeline (Multi-stage) | 14/15 | 152.9s | [114.1s, 191.7s] | 10,713 | 18,144 | $0.0049 | 93.3% | 6.7% |

_Generated by `scripts/render_readme_table.py` from a recorded benchmark run (5 words x 3 iterations per strategy; 112 valid runs feed the latency stats). The 95% CI is a normal approximation over the valid-run latencies (see `confidence_interval_95`); with this small n it is an optimistic lower bound on uncertainty, and sub-second gaps between adjacent strategies overlap heavily (they are within the margin, not a ranking)._
<!-- BENCHMARK_TABLE:END -->

> **How this table is verified:** the 22.0s to 17.2s figures come from a **manual n=120 run**, not a CI-gated benchmark. `ci.yml` runs pytest+ruff against a fully offline/mocked provider (deterministic, zero network calls) and does not re-run or assert on live latency numbers. What IS gated automatically today: (1) the logic that decides which strategy is reported as "fastest fully valid" (`tests/test_compare_benchmarks.py`), (2) one test file per strategy asserting contract + output validity (`tests/test_strategy_*.py`), and (3) the **replay benchmark gate** (`benchmarks/` + `.github/workflows/bench.yml`): a nightly job re-runs all 8 strategies against a deterministic replay provider built from the recorded runs and fails if any strategy's relative p50 latency drifts beyond a defined threshold. The replay gate protects the orchestration code and the relative ordering; it does NOT re-verify the absolute live-API numbers, which remain pending live re-verification.
>
> **Test words:** `hana`, `kuusi`, `juosta`, `vanha`, `silta` — deliberately chosen for varying lexical ambiguity (hana = 3+ meanings vs. silta = 1 clear meaning).
>
> **On ranking:** each strategy is averaged over only n=15 runs with wide LLM-side variance. Sub-second gaps between adjacent strategies are within the margin, not a clear ordering — e.g. Lazy Optimized (16.1 ±8.6s) and Structured Cascade (17.2 ±4.3s) overlap heavily. Cost is an estimate (token counts × published rates), not a billed figure.
>
> **On "Valid Output Rate":** this metric is not strictly apples-to-apples across strategies, and the right axis to read it on is **schema enforcement**, not multi-stage vs. single-shot. Only Monolithic (No Schema) is validated against **raw one-shot JSON** the model emits, where structure can genuinely fail. Every strategy that passes a `response_schema` to the API — `Monolithic (Strict Schema)` (one schema-constrained call), `cascade` and `pipeline` (multi-stage, which additionally **assemble their output in code** via `stage_assembly.assemble_examples` over per-stage schema-constrained sub-calls) — gets its structural shape largely guaranteed by the SDK before the validator runs. Read every schema-enforced 100% as "the validator only had to add CEFR completeness and headword policy on top of an already structurally-valid payload", not as the same test the no-schema baseline passes. (Even the schema isn't fully tautological: a Stage 2 schema doesn't force the exact six CEFR levels or "no duplicates", so the validator's completeness checks can still fail.)

---

## Key Findings

### 1. Root Cause: Instruction Friction

The reported 62k-token spike (not reproduced in our runs, but consistent with the elevated thought usage we did measure) plausibly emerges from three competing cognitive modes in a single prompt:

1. **Creative generation** — pedagogically appropriate CEFR-leveled Finnish sentences
2. **Deterministic transformation** — 10 specific phonological rules for `spokenFi`
3. **Strict JSON structure** — nested arrays, exact field names, enum values

The model constantly re-derives rules while questioning whether its creative output violates structural constraints, creating a reasoning spiral.

### 2. Structured Cascade is the Production Answer

The **Structured Cascade** decomposes the task into 3 specialized stages with per-stage thinking controls:

| Stage | Task | Thinking Level | Temperature |
|---|---|---|---|
| Stage 1 | Extract meanings & definitions | `LOW` | 0.2 |
| Stage 2 | Generate CEFR examples (per meaning) | `LOW` | 0.7 |
| Stage 3 | SpokenFi transformation (per meaning, after Stage 2) | `MINIMAL` | 0.0 |

**Result (single manual n=120 run, pending CI-gated live verification):** 17.2s average latency (95% CI [15.0s, 19.4s], n=15), with 0 validation failures in that run — a promising sign, not a reliability guarantee at n=15. Each meaning is processed in parallel via `asyncio.gather`; within a single meaning, Stage 2 runs before Stage 3 because Stage 3 transforms Stage 2's output.

> **On "parallel":** every mention of "parallel"/"concurrent" in this README refers to
> **async I/O orchestration** (`asyncio.gather` over concurrent network calls to the
> Gemini API), not CPU-bound compute parallelism. The 8 strategies compared are
> different ways of sequencing and batching those network calls — none of them do
> multi-threaded or multi-process computation.

### 3. Pipeline is an Anti-Pattern

The most counterintuitive finding: **Pipeline (sequential multi-stage) is the worst strategy at 152.9s**. Without thinking controls, Stage 3 (spokenFi) enters 45-second reasoning spirals on every meaning, one at a time. Cascade avoids this by capping Stage 3's thinking to `MINIMAL` and running meanings in parallel.

### 4. Pro Model Does Not Solve Architectural Problems

`gemini-3.1-pro-preview` averaged **54.7s at $0.034/call** — 19x more expensive than Flash with **lower reliability (86.7%)**. For structured generation, architecture beats raw model power.

### 5. Suppressing Thinking is Fast but Fragile

In **this monolithic prompt**, `thinking_level=LOW` produced the fastest results (8.2s) and collapsed thought usage to **~0 tokens** in our runs — but it also sacrificed **6.7% of outputs** to JSON validation failures. Acceptable with retry logic; not suitable for fire-and-forget production.

> **Note — `LOW` is not a guaranteed zero.** The ~0 thought tokens above is an empirical observation for the *monolithic* task, not a property of the level. The **Structured Cascade also uses `thinking_level=LOW`** in Stages 1–2 (`strategies/cascade/runner.py:138,161`) yet still measures **3,862 avg / 10,195 max thought tokens**. Whether `LOW` collapses thinking to zero depends on the task and prompt, not on the level alone.

---

## Strategies Tested

| # | Strategy | Description | Key Insight |
|---|----------|-------------|-------------|
| 1 | Monolithic (No Schema) | Original prompt — baseline control | 22.0s avg (95% CI [19.8s, 24.2s]), 0/15 validation failures |
| 2 | Monolithic (Strict Schema) | API-level `response_schema` enforcement | +31% latency vs baseline due to schema compliance overhead |
| 3 | Optimized Monolithic | Shorter prompt with Few-Shot patterns | Fast but 26.7% failure rate |
| 4 | Lazy Optimized (A1-B1) | Only generates 3 CEFR levels instead of 6 | Best cost/performance for partial output |
| 5 | **Structured Cascade** | Per-stage thinking + parallel execution | **Production pick: 17.2s (95% CI [15.0s, 19.4s]), 0/15 validation failures in the single run — within the margin of the top fully-valid strategies** |
| 6 | Pipeline (Multi-stage) | Sequential decomposition, no thinking control | Worst: 152.9s, reasoning spirals in Stage 3 |
| 7 | Thinking Budget (LOW) | Monolithic with `thinking_level=LOW` | Fastest at 8.2s, but 6.7% malformed outputs |
| 8 | Pro Model | `gemini-3.1-pro-preview` | 19x cost, lower reliability than architected Flash |

---

## Project Structure

```
├── prompts.py               # All prompt variants, system messages, schemas
├── .env                     # GOOGLE_API_KEY
├── scripts/
│   ├── compare_benchmarks.py       # Main orchestrator (live runs, report generation)
│   ├── salvage.py                  # Rebuild reports from a run log
│   ├── measure_concurrency_fase2.py# Structural concurrency (mocked provider)
│   ├── measure_concurrency_real.py # Real concurrent-load benchmark (live API)
│   └── merge_extended_corpus.py    # One-off merge of the two real datasets
├── strategies/
│   ├── monolithic/          # Baseline + strict-schema variant (run_monolithic_schema)
│   ├── optimized_monolithic/# Shortened few-shot prompt
│   ├── lazy_optimized/      # Partial CEFR (A1-B1 only)
│   ├── cascade/             # Structured Cascade (production pick)
│   ├── pipeline/            # Sequential multi-stage
│   ├── thinking_budget/     # thinking_level=LOW cap
│   ├── pro_model/           # gemini-3.1-pro-preview
│   ├── providers.py         # InferenceProvider protocol + Gemini adapter
│   ├── stage_assembly.py    # Assembles multi-stage output (assemble_examples)
│   ├── output_validation.py # JSON + CEFR structure validator
│   └── utils.py             # Shared: cost rates, metrics, API helpers
├── benchmarks/              # Deterministic replay harness (no network, no key)
│   ├── fixtures/            # Versioned fixtures derived from the recorded runs
│   ├── replay_provider.py   # InferenceProvider that replays recorded latencies
│   ├── run.py               # p50/p95/p99 + CI95 to results.json; --check = gate
│   └── results.json         # Versioned replay baseline the nightly gate compares against
├── benchmark_results/       # Generated reports, raw JSON, drafts
└── dashboard/               # Visualization UI
    ├── index.html
    ├── index.css
    └── app.js
```

---

## Quick Start

```bash
# 1. Create the virtualenv and install dependencies (pyproject.toml declares
#    the ranges; requirements.lock pins the exact versions CI runs with)
python -m venv venv
./venv/bin/pip install -e . -c requirements.lock

# Then copy .env.template to .env and set GOOGLE_API_KEY.

# 2. Quick smoke test (1 word, 1 iteration)
./venv/bin/python -m scripts.compare_benchmarks --words silta --iterations 1

# 3. Full benchmark (all 8 strategies, 5 words, 3 iterations = 120 runs;
#    multi-stage strategies emit several Gemini calls per run, so the real
#    API-call count is higher)
./venv/bin/python -m scripts.compare_benchmarks \
  --strategies monolithic monolithic_schema optimized_monolithic lazy_optimized pipeline cascade thinking_budget pro_model \
  --iterations 3

# 3b. Offline replay benchmark (no key, no cost): p50/p95/p99 + regression gate
./venv/bin/python -m benchmarks.run --check --iterations 15

# 4. View dashboard locally
./venv/bin/python -m http.server 8080
# Open http://localhost:8080/dashboard/
# (Or view the deployed version: https://damiansire.github.io/gemini-inference-framework/)
```

## Custom Runs

```bash
# Test specific strategies
./venv/bin/python -m scripts.compare_benchmarks --strategies monolithic cascade --iterations 5

# Test specific words
./venv/bin/python -m scripts.compare_benchmarks --words hana kuusi --iterations 3

# Adjust timeout (default: 180s)
./venv/bin/python -m scripts.compare_benchmarks --timeout 240
```

---

## Recommendations for Production

All figures below are from the single manual n=120 run (n=15 per strategy, pending CI-gated live verification); the parenthetical latencies are point estimates over a small, high-variance sample, not guarantees:

1. **For full dictionary entries (6 CEFR levels + spokenFi):** Use **Structured Cascade** (17.2s, 95% CI [15.0s, 19.4s], 0/15 validation failures, $0.002/call in that run).
2. **For maximum speed with retry tolerance:** `thinking_level=LOW` monolithic (8.2s, required ~7% retry rate).
3. **For partial content (A1-B1 only):** Lazy Optimized (16.1s, 95% CI [11.8s, 20.5s], 0/15 validation failures, lowest cost).
4. **Avoid:** Pipeline without thinking controls. Pro Model for structured generation tasks.

---

## CI, replay gate, provider pluggability, and real load testing

### `ci.yml` vs `bench.yml` vs `live-eval.yml` vs `regen-readme-table.yml`

`ci.yml` (pytest + ruff) is **100% offline/mocked** by design (see its own
header comment): it gates every push/PR without needing a secret or spending
real money. The suite includes one test file per strategy
(`tests/test_strategy_*.py`, 8/8) asserting the common dict contract and
output validity against the same replay provider the benchmark harness uses.

`.github/workflows/bench.yml` is the **replay benchmark gate**
(manual-dispatch + nightly): it re-runs all 8 strategies N times against the
deterministic `ReplayProvider` (versioned fixtures in `benchmarks/fixtures/`,
derived from the recorded real runs), recomputes p50/p95/p99 + n + CI95, and
**fails if any strategy's relative p50 latency drifts beyond a defined
threshold** (default +/-25%) versus the versioned baseline
(`benchmarks/results.json`). Because latencies are replayed, a drift can only
mean the orchestration code changed (parallel became sequential, calls were
added or lost) or the fixture/baseline needs an intentional regeneration. It
verifies the latency *profile* of the code, not the live API numbers.

`.github/workflows/live-eval.yml` is the live complement: a
**manual-dispatch + weekly** job that pegs a cheap subset (1 word, 1
iteration, the lightest strategy) against the **real, paid** Gemini API and
uploads the result as a workflow artifact, to catch drift a mock can never
show (real latency, real schema/response shape changes). It does **not** gate
merges: a transient 429 or a slow week shouldn't block a PR.

It requires a `GOOGLE_API_KEY` **repository secret** (Settings → Secrets and
variables → Actions) — configuring it is a one-time step only the repo owner
can do (same reasoning as `NPM_TOKEN` in the release pipelines: it's a
credential tied to a personal account). Without the secret the job fails
fast with a clear message instead of hanging or dumping a raw traceback —
verified locally by running `scripts/compare_benchmarks.py` with `GOOGLE_API_KEY`/
`GEMINI_API_KEY` both absent from the environment: exit code 1, message
`GOOGLE_API_KEY is not set. Copy .env.template to .env and fill in a real
key`.

`.github/workflows/regen-readme-table.yml` closes the loop on the headline
table specifically. It is **manual-dispatch + monthly** (it hits the paid API,
so it does not run per-push) and, gated on the same `GOOGLE_API_KEY` secret,
**re-measures all 8 strategies with a larger, configurable n**, recomputes the
means and 95% CIs, regenerates the leaderboard via
`scripts/render_readme_table.py`, and opens a PR with the refreshed
`benchmark_results/readme_leaderboard_run.json` + README table. This is why the
table stops being a frozen unverified number: it is either re-measured and
updated, or the section header already flags it as a single manual run.

The table itself is a **gated artifact**, not prose: it is generated between the
`<!-- BENCHMARK_TABLE:START/END -->` markers from the versioned dataset, and
`tests/test_render_readme_table.py` (part of the offline `ci.yml` suite) fails
if the committed table drifts from that data. Regenerate locally with:

```bash
python -m scripts.render_readme_table --write   # rewrite the table in place
python -m scripts.render_readme_table --check    # gate: fail if out of sync
```

### Replay harness (`benchmarks/`)

```bash
# Regenerate the fixture from the recorded real datasets (versioned inputs)
python -m benchmarks.generate_fixture

# Run the replay benchmark and rewrite the baseline (benchmarks/results.json)
python -m benchmarks.run --iterations 15

# Gate mode: compare a fresh replay run against the versioned baseline
python -m benchmarks.run --check --iterations 15
```

The fixture stores the end-to-end durations of every valid recorded run (both
real datasets in `benchmark_results/`, n=240 combined) plus canned responses;
the provider replays them at `time_scale` (default 0.05) so a full gated run
takes a few minutes and zero dollars. The gate compares the *measured*
relative p50 of a fresh run against the *expected* relative p50 stored in
`benchmarks/results.json` (computed analytically from the fixture, so it is
machine-independent), adjusting the expectation by a live-calibrated
per-sleep event-loop overhead so the check is portable across OS timer
resolutions. Honest scope note: for cascade/pipeline the per-stage
split of each recorded duration is a documented convention (the datasets only
recorded e2e), so the replay preserves real e2e distributions and call
structure, not per-stage timings.

### Provider pluggability (`strategies/providers.py`)

The framework does not talk to `google.genai` directly: every runner goes
through `utils.get_provider()`, which returns an `InferenceProvider`
(`Protocol`, structurally typed — no base class required). `GeminiProvider`
is the only production implementation today, but `utils.set_provider(...)`
lets any object satisfying the two-method protocol
(`generate_content`/`generate_content_stream`) replace it without touching a
single strategy runner.

`tests/test_providers.py` proves this with a **mock second-backend
provider** (`SecondBackendProvider`, structurally unrelated to
`GeminiProvider`) run end-to-end through `run_monolithic_schema`: the dict
contract and `validate_dictionary_output` both pass against it, same as
against the real Gemini path. What this does **not** cover: a real paid
second vendor (OpenAI/Anthropic/etc.). That's pending a second API key; once
available, the remaining work is a concrete adapter class implementing
`InferenceProvider` for that SDK, injected via `utils.set_provider(...)`
before a normal `scripts/compare_benchmarks.py` run, no strategy code changes.

### Real concurrent-load benchmark (`scripts/measure_concurrency_real.py`)

`scripts/measure_concurrency_fase2.py` measures **structural** concurrency
(in-flight call count) against a mocked provider: useful for verifying the
Semaphore cap, useless for real latency under load.
`scripts/measure_concurrency_real.py` fires N real simultaneous calls
(`asyncio.gather`, N configurable via `--concurrency`, 10-20 per gif-adn-2)
at the live API and reports real p50/p95/p99 latency:

```bash
python -m scripts.measure_concurrency_real --concurrency 15
```

It raises `GEMINI_MAX_CONCURRENCY` to match `--concurrency` before running so
the shared Semaphore (default 5) doesn't silently throttle the requested
load. Results are saved to `benchmark_results/concurrency_load_data.json`.

---

## Requirements

- Python 3.10+
- `google-genai` SDK
- `python-dotenv`
- Google API Key with Gemini access (in `.env`)

---

*Benchmark methodology: UUID+epoch cache busting per call, randomized execution order, model warmup, output validation (JSON structure + CEFR level completeness). Models: `gemini-3-flash-preview`, `gemini-3.1-pro-preview`.*
