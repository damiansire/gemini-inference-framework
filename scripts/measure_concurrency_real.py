"""Benchmark de carga concurrente REAL contra la API paga de Gemini (gif-adn-2).

Diferencia con `measure_concurrency_fase2.py`: ese archivo mide concurrencia
ESTRUCTURAL (cuantas requests in-flight dispara el fan-out de una estrategia)
contra un provider MOCKEADO, sin red. Este archivo mide LATENCIA REAL bajo
carga concurrente real: dispara N llamadas simultaneas (asyncio.gather) contra
la API de Gemini y reporta p50/p95/p99 de duracion, que un mock no puede
mostrar (el mock no tiene rate limiting, jitter de red, ni contencion real de
cuota).

Requiere GOOGLE_API_KEY (falla rapido y explicito si falta, mismo criterio que
compare_benchmarks.py). Corre gasto real: N llamadas a la estrategia mas
liviana por defecto (optimized_monolithic), N configurable via --concurrency
(10-20 por default 15, siguiendo el pedido de gif-adn-2).

Uso (desde la raiz del repo):
    python -m scripts.measure_concurrency_real --concurrency 15
    python -m scripts.measure_concurrency_real --concurrency 10 --strategy monolithic_schema
"""

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv

from prompts import TEST_WORDS
from scripts.compare_benchmarks import RESULTS_DIR, STRATEGIES

load_dotenv()


def _percentile(sorted_values, pct):
    """Percentil por interpolacion lineal (nearest-rank simplificado).

    n tipico aca es 10-20: no amerita numpy solo para esto. Con n chico el p99
    colapsa casi al maximo, que es lo esperado y se documenta en el output.
    """
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100)
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


async def run_concurrent_load(strategy_key, concurrency, word, timeout):
    strategy = STRATEGIES[strategy_key]
    runner = strategy["runner"]

    async def _one_call(index):
        salt = f"{uuid.uuid4().hex[:8]}-{index}"
        start = time.time()
        result = await runner(word, salt=salt, timeout=timeout)
        wall_duration = time.time() - start
        return {
            "index": index,
            "success": result.get("success", False),
            "timed_out": result.get("timed_out", False),
            "reported_duration": result.get("duration", 0),
            "wall_duration": wall_duration,
            "error": result.get("error"),
        }

    batch_start = time.time()
    results = await asyncio.gather(*(_one_call(i) for i in range(concurrency)))
    batch_wall = time.time() - batch_start
    return results, batch_wall


def summarize_load(results, batch_wall, concurrency):
    successful = [r for r in results if r["success"]]
    durations = sorted(r["wall_duration"] for r in successful)

    summary = {
        "concurrency": concurrency,
        "total_calls": len(results),
        "successful_calls": len(successful),
        "failed_calls": len(results) - len(successful),
        "timed_out_calls": sum(1 for r in results if r["timed_out"]),
        "batch_wall_seconds": batch_wall,
        "p50_seconds": _percentile(durations, 50),
        "p95_seconds": _percentile(durations, 95),
        "p99_seconds": _percentile(durations, 99),
        "min_seconds": durations[0] if durations else None,
        "max_seconds": durations[-1] if durations else None,
    }
    if durations:
        summary["mean_seconds"] = statistics.mean(durations)
    return summary


async def main():
    parser = argparse.ArgumentParser(
        description="Real concurrent-load benchmark against the live Gemini API"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=15,
        help="Simultaneous in-flight calls (gif-adn-2 asks for 10-20)",
    )
    parser.add_argument(
        "--strategy",
        default="optimized_monolithic",
        choices=list(STRATEGIES.keys()),
        help="Strategy to load-test (default: cheapest/fastest, to bound real cost)",
    )
    parser.add_argument("--word", default=TEST_WORDS[0], help="Word to send on every call")
    parser.add_argument("--timeout", type=int, default=180, help="Per-call timeout in seconds")
    parser.add_argument(
        "--output", default="concurrency_load_data.json", help="Filename inside benchmark_results/"
    )
    args = parser.parse_args()

    if not os.environ.get("GOOGLE_API_KEY"):
        print(
            "\nGOOGLE_API_KEY is not set. Copy .env.template to .env and fill in a real key:\n"
            "  cp .env.template .env\n"
        )
        raise SystemExit(1)

    # El Semaphore compartido (strategies/utils.py, default 5) capea el
    # in-flight real independientemente de cuanto pida --concurrency. Para que
    # esta medicion refleje la concurrencia PEDIDA (no la del semaphore
    # default) se sube el limite al nivel del batch antes de arrancar.
    os.environ["GEMINI_MAX_CONCURRENCY"] = str(args.concurrency)

    print("=" * 70)
    print("  REAL CONCURRENT LOAD BENCHMARK (gif-adn-2)")
    print(f"  Strategy: {STRATEGIES[args.strategy]['name']} | word='{args.word}'")
    print(f"  Concurrency: {args.concurrency} simultaneous real calls")
    print("=" * 70)

    results, batch_wall = await run_concurrent_load(
        args.strategy, args.concurrency, args.word, args.timeout
    )
    summary = summarize_load(results, batch_wall, args.concurrency)

    print(f"\nBatch wall time: {batch_wall:.2f}s for {args.concurrency} concurrent calls")
    print(f"Successful: {summary['successful_calls']}/{summary['total_calls']}")
    print(
        f"p50={summary['p50_seconds']:.2f}s  p95={summary['p95_seconds']:.2f}s  "
        f"p99={summary['p99_seconds']:.2f}s  max={summary['max_seconds']:.2f}s"
    )

    os.makedirs(RESULTS_DIR, exist_ok=True)
    output_path = os.path.join(RESULTS_DIR, args.output)
    payload = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "strategy": args.strategy,
            "word": args.word,
            "requested_concurrency": args.concurrency,
            "gemini_max_concurrency_env": os.environ["GEMINI_MAX_CONCURRENCY"],
            "timeout": args.timeout,
        },
        "summary": summary,
        "raw_calls": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
