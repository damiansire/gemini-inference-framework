| Field      | Description |
|------------|------------|
| Disclaimer | This repository represents only my personal views and approach and has not been peer-reviewed; do not take it as absolute truth until the corresponding review is completed. |
| Status     | Pending peer review |


# Gemini Reasoning Explosion — Empirical Benchmark & Mitigation Suite

> **TL;DR:** A Finnish dictionary prompt causes `gemini-3-flash-preview` to consume **62k+ thought tokens** and take **4 minutes 19 seconds**. We built a benchmark of **120 controlled API calls** across **8 architectural strategies** and found that a **Structured Cascade** architecture reduces this to **17.2s with 100% reliability** — without changing the prompt content.

---

## Context: The Problem

This project originated from a [GenAI Circle discussion] reported extreme latency and token waste with `gemini-3-flash-preview`:

| Metric | Reported Value |
|---|---|
| Duration | **4 minutes 19 seconds** |
| Input Tokens | ~3,400 |
| Output Tokens | ~1,069 |
| Thought Tokens | **62,910** |

The prompt generates structured JSON dictionary entries for Finnish words, requiring CEFR-leveled examples and phonological transformations to spoken Finnish (`spokenFi`). Our working hypothesis: the model enters **reasoning loops** due to competing constraints — strict JSON + creative generation + deterministic linguistic rules.

---

## Benchmark Results (n=120)

**8 strategies × 5 words × 3 iterations** — with UUID+epoch cache busting, randomized execution order, model warmup, and structural output validation.

| Strategy | Avg Latency (±std) | Avg Thought Tokens | Max Thought | Avg Cost (USD, est.) | Success Rate | Failure Rate |
|---|---|---|---|---|---|---|
| **Thinking Budget (LOW)** | **8.2s** ±2.2s ⚡ | **0** | 0 | $0.0007 | 93.3% | 6.7% |
| **Lazy Optimized (A1-B1)** | **16.1s** ±8.6s | 2,586 | 6,620 | $0.0014 | 100% | 0% |
| **Structured Cascade** | **17.2s** ±4.3s ✅ | 3,862 | 10,195 | $0.0023 | **100%** | **0%** |
| Optimized Monolithic | 20.7s ±8.0s | 2,645 | 5,785 | $0.0015 | 73.3% | 26.7% |
| Monolithic (No Schema) | 22.0s ±4.4s | 2,648 | 4,498 | $0.0018 | 100% | 0% |
| Monolithic (Strict Schema) | 28.9s ±7.3s | 4,049 | 6,597 | $0.0024 | 100% | 0% |
| Pro Model (3.1) | 54.7s ±10.6s | 4,822 | 7,420 | **$0.0340** 💸 | 86.7% | 13.3% |
| **Pipeline (Multi-stage)** | **152.9s** ±74.0s 🐌 | **10,713** | **18,144** | $0.0049 | 93.3% | 6.7% |

> **Test words:** `hana`, `kuusi`, `juosta`, `vanha`, `silta` — deliberately chosen for varying lexical ambiguity (hana = 3+ meanings vs. silta = 1 clear meaning).
>
> **On ranking:** each strategy is averaged over only n=15 runs with wide LLM-side variance. Sub-second gaps between adjacent strategies are within the margin, not a clear ordering — e.g. Lazy Optimized (16.1 ±8.6s) and Structured Cascade (17.2 ±4.3s) overlap heavily. Cost is an estimate (token counts × published rates), not a billed figure.

---

## Key Findings

### 1. Root Cause: Instruction Friction

The 62k thought tokens emerge from three competing cognitive modes in a single prompt:

1. **Creative generation** — pedagogically appropriate CEFR-leveled Finnish sentences
2. **Deterministic transformation** — 10 specific phonological rules for `spokenFi`
3. **Strict JSON structure** — nested arrays, exact field names, enum values

The model constantly re-derives rules while questioning whether its creative output violates structural constraints, creating a reasoning spiral.

### 2. Structured Cascade is the Production Answer

The **Structured Cascade** decomposes the task into 3 specialized stages with per-stage thinking controls:

| Stage | Task | Thinking Level | Temperature |
|---|---|---|---|
| Stage 1 | Extract meanings & definitions | `LOW` | 0.2 |
| Stage 2 | Generate CEFR examples (parallel) | `LOW` | 0.7 |
| Stage 3 | SpokenFi transformation (parallel) | `MINIMAL` | 0.0 |

**Result:** 17.2s average with **100% success rate** across all 15 runs. Stage 2 and 3 run in parallel via `asyncio.gather`.

### 3. Pipeline is an Anti-Pattern

The most counterintuitive finding: **Pipeline (sequential multi-stage) is the worst strategy at 152.9s**. Without thinking controls, Stage 3 (spokenFi) enters 45-second reasoning spirals on every meaning, one at a time. Cascade avoids this by capping Stage 3's thinking to `MINIMAL` and running meanings in parallel.

### 4. Pro Model Does Not Solve Architectural Problems

`gemini-3.1-pro-preview` averaged **54.7s at $0.034/call** — 19x more expensive than Flash with **lower reliability (86.7%)**. For structured generation, architecture beats raw model power.

### 5. Suppressing Thinking is Fast but Fragile

`thinking_level=LOW` produces the fastest results (8.2s) with **zero thought tokens**, but sacrifices **6.7% of outputs** to JSON validation failures. Acceptable with retry logic; not suitable for fire-and-forget production.

---

## Strategies Tested

| # | Strategy | Description | Key Insight |
|---|----------|-------------|-------------|
| 1 | Monolithic (No Schema) | Original prompt — baseline control | 22s avg, 100% reliable |
| 2 | Monolithic (Strict Schema) | API-level `response_schema` enforcement | +31% latency vs baseline due to schema compliance overhead |
| 3 | Optimized Monolithic | Shorter prompt with Few-Shot patterns | Fast but 26.7% failure rate |
| 4 | Lazy Optimized (A1-B1) | Only generates 3 CEFR levels instead of 6 | Best cost/performance for partial output |
| 5 | **Structured Cascade** | Per-stage thinking + parallel execution | **Production pick — 17.2s ±4.3s, 100% success (within the margin of the top fully-valid strategies)** |
| 6 | Pipeline (Multi-stage) | Sequential decomposition, no thinking control | Worst: 152.9s, reasoning spirals in Stage 3 |
| 7 | Thinking Budget (LOW) | Monolithic with `thinking_level=LOW` | Fastest at 8.2s, but 6.7% malformed outputs |
| 8 | Pro Model | `gemini-3.1-pro-preview` | 19x cost, lower reliability than architected Flash |

---

## Project Structure

```
├── compare_benchmarks.py    # Main orchestrator (120+ runs, report generation)
├── prompts.py               # All prompt variants, system messages, schemas
├── .env                     # GOOGLE_API_KEY
├── strategies/
│   ├── monolithic/          # Baseline strategy
│   ├── monolithic_schema/   # Strict schema enforcement
│   ├── optimized_monolithic/# Shortened few-shot prompt
│   ├── lazy_optimized/      # Partial CEFR (A1-B1 only)
│   ├── cascade/             # ✅ Structured Cascade (production)
│   ├── pipeline/            # Sequential multi-stage  
│   ├── thinking_budget/     # thinking_level=LOW cap
│   ├── pro_model/           # gemini-3.1-pro-preview
│   ├── output_validation.py # JSON + CEFR structure validator
│   └── utils.py             # Shared: cost rates, metrics, API helpers
├── benchmark_results/       # Generated reports, raw JSON, drafts
├── docs/
│   ├── ARCHITECTURE.md      # Technical analysis of reasoning explosion
│   └── ...
└── dashboard/               # Visualization UI
    ├── index.html
    ├── index.css
    └── app.js
```

---

## Quick Start

```bash
# 1. Install dependencies
./venv/bin/pip install google-genai python-dotenv

# 2. Quick smoke test (1 word, 1 iteration)
./venv/bin/python compare_benchmarks.py --words silta --iterations 1

# 3. Full benchmark (all 8 strategies, 5 words, 3 iterations = 120 calls)
./venv/bin/python compare_benchmarks.py \
  --strategies monolithic monolithic_schema optimized_monolithic lazy_optimized pipeline cascade thinking_budget pro_model \
  --iterations 3

# 4. View dashboard
./venv/bin/python -m http.server 8080
# Open http://localhost:8080/dashboard/
```

## Custom Runs

```bash
# Test specific strategies
./venv/bin/python compare_benchmarks.py --strategies monolithic cascade --iterations 5

# Test specific words
./venv/bin/python compare_benchmarks.py --words hana kuusi --iterations 3

# Adjust timeout (default: 180s)
./venv/bin/python compare_benchmarks.py --timeout 240
```

---

## Recommendations for Production

1. **For full dictionary entries (6 CEFR levels + spokenFi):** Use **Structured Cascade** — 17.2s, 100% reliability, $0.002/call.
2. **For maximum speed with retry tolerance:** `thinking_level=LOW` monolithic — 8.2s, requires ~7% retry rate.
3. **For partial content (A1-B1 only):** Lazy Optimized — 16.1s, 100% reliable, lowest cost.
4. **Avoid:** Pipeline without thinking controls. Pro Model for structured generation tasks.

---

## Requirements

- Python 3.10+
- `google-genai` SDK
- `python-dotenv`
- Google API Key with Gemini access (in `.env`)

---

*Benchmark methodology: UUID+epoch cache busting per call, randomized execution order, model warmup, output validation (JSON structure + CEFR level completeness). Models: `gemini-3-flash-preview`, `gemini-3.1-pro-preview`.*
