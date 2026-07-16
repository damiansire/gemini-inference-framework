"""Harness de benchmark en modo replay: reproducible, sin red, sin API key.

Corre las 8 estrategias registradas N veces cada una contra el
``ReplayProvider`` (fixtures versionadas en ``benchmarks/fixtures/``), valida
cada salida con el mismo quality gate del benchmark real
(``_normalize_result``) y emite p50/p95/p99 + n + IC95 por estrategia a
``benchmarks/results.json``.

Modos:
    python -m benchmarks.run                  # corre y reescribe results.json
    python -m benchmarks.run --check          # corre y compara contra results.json

``--check`` es el gate de regresion: falla (exit 1) si alguna corrida no
valida, o si la latencia RELATIVA medida de una estrategia (p50 vs el baseline
monolithic) se desvia mas alla de ``--threshold`` en CUALQUIER direccion del
valor ESPERADO versionado en ``results.json``. El esperado se computa
analiticamente de la fixture (las duraciones grabadas, cicladas y escaladas),
asi que es identico en cualquier maquina; lo medido incluye el overhead real
del event loop. Una mejora "gratis" tambien falla a proposito: en modo replay
las latencias estan grabadas, asi que un corrimiento grande solo puede
significar que el codigo de orquestacion cambio (se serializo lo paralelo, se
agregaron o perdieron llamadas) o que la fixture/baseline quedaron
desactualizadas y hay que regenerarlas explicitamente.

Que NO verifica: los numeros absolutos contra la API viva (eso es
``live-eval.yml`` y corridas manuales; ver README).
"""

import argparse
import asyncio
import builtins
import contextlib
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.replay_provider import ReplayProvider, load_fixture
from scripts.compare_benchmarks import (
    STRATEGIES,
    _normalize_result,
    confidence_interval_95,
)
from strategies import utils

BENCH_DIR = Path(__file__).resolve().parent
RESULTS_PATH = BENCH_DIR / "results.json"
DEFAULT_ITERATIONS = 15
DEFAULT_THRESHOLD = 0.25
BASELINE_STRATEGY = "monolithic"
REPLAY_WORD = "hana"


def percentile(sorted_values, pct):
    """Percentil por interpolacion lineal; n chico (10-30) no amerita numpy."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (pct / 100)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    fraction = rank - low
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * fraction


@contextlib.contextmanager
def _silence_runner_prints():
    """Los runners multi-etapa imprimen progreso por stage; a N iteraciones son
    cientos de lineas que entierran el reporte del harness."""
    real_print = builtins.print
    builtins.print = lambda *args, **kwargs: None
    try:
        yield
    finally:
        builtins.print = real_print


async def _run_strategy(provider, strategy_key, iterations, timeout):
    durations = []
    failures = []
    for iteration in range(iterations):
        provider.begin_run(strategy_key, iteration)
        with _silence_runner_prints():
            raw = await STRATEGIES[strategy_key]["runner"](
                REPLAY_WORD, salt=f"replay-{iteration}", timeout=timeout
            )
        result = _normalize_result(strategy_key, raw)
        if result["success"]:
            durations.append(result["duration"])
        else:
            failures.append(result.get("error") or "unknown failure")
    return durations, failures


def _summarize(durations, failures, time_scale):
    ordered = sorted(durations)
    summary = {
        "n": len(durations),
        "failures": len(failures),
        "failure_messages": failures[:3],
        "p50_s": percentile(ordered, 50),
        "p95_s": percentile(ordered, 95),
        "p99_s": percentile(ordered, 99),
        "mean_s": statistics.mean(ordered) if ordered else None,
        "ci95": confidence_interval_95(ordered),
    }
    # Equivalente descalado: el replay duerme duracion_grabada * time_scale,
    # asi que p50_s / time_scale aproxima la escala de la corrida real grabada.
    if summary["p50_s"] is not None and time_scale > 0:
        summary["p50_equivalent_real_s"] = summary["p50_s"] / time_scale
    return summary


async def _run_all(fixture, iterations, timeout):
    provider = ReplayProvider(fixture)
    original_provider = utils.get_provider()
    utils.set_provider(provider)
    try:
        summaries = {}
        for strategy_key in fixture["strategies"]:
            print(f"  replay {strategy_key} x{iterations}...", flush=True)
            durations, failures = await _run_strategy(provider, strategy_key, iterations, timeout)
            summaries[strategy_key] = _summarize(durations, failures, fixture["time_scale"])
        return summaries
    finally:
        utils.set_provider(original_provider)
        utils.reset_inference_semaphore()


def _attach_relatives(summaries):
    baseline_p50 = summaries.get(BASELINE_STRATEGY, {}).get("p50_s")
    for summary in summaries.values():
        if baseline_p50 and summary["p50_s"] is not None:
            summary["relative_p50_vs_monolithic"] = summary["p50_s"] / baseline_p50
        else:
            summary["relative_p50_vs_monolithic"] = None
    return summaries


def _expected_stats(fixture, iterations):
    """Percentiles ESPERADOS, computados analiticamente de la fixture.

    En replay la duracion e2e de una corrida es (por construccion del
    stage_split, que suma 1.0) la duracion grabada por time_scale; lo unico que
    agrega la ejecucion real es overhead de event loop. Este esperado es
    deterministico y no depende de la maquina, por eso es el valor contra el
    que gatea --check (el p50 MEDIDO de una corrida fresca debe caer cerca).
    """
    scale = fixture["time_scale"]
    expected = {}
    for key, spec in fixture["strategies"].items():
        recorded = spec["durations_s"]
        sample = sorted(recorded[i % len(recorded)] * scale for i in range(iterations))
        expected[key] = {"expected_p50_s": percentile(sample, 50)}
    baseline_p50 = expected.get(BASELINE_STRATEGY, {}).get("expected_p50_s")
    for stats in expected.values():
        if baseline_p50:
            stats["expected_relative_p50"] = stats["expected_p50_s"] / baseline_p50
        else:
            stats["expected_relative_p50"] = None
    return expected


async def _calibrate_sleep_overhead(samples=8, base_sleep_s=0.05):
    """Mide el overhead real de un ``asyncio.sleep`` en ESTA maquina.

    La resolucion del timer varia por plataforma (Linux ~1ms; Windows puede
    agregar decenas de ms por sleep). Ese overhead es por-llamada, asi que
    penaliza mas a las estrategias con mas sleeps secuenciales (pipeline 7,
    cascade 3, single 1) y sesgaria el gate relativo si no se compensa. Se
    calibra en vivo y se suma al esperado analitico de cada estrategia segun
    su numero ESTRUCTURAL de sleeps encadenados.
    """
    overheads = []
    for _ in range(samples):
        start = time.perf_counter()
        await asyncio.sleep(base_sleep_s)
        overheads.append(time.perf_counter() - start - base_sleep_s)
    return max(statistics.mean(overheads), 0.0)


def _chained_sleeps(spec, num_meanings):
    """Sleeps SECUENCIALES por corrida segun la estructura de la estrategia."""
    if spec["kind"] == "multistage_parallel":
        return 3  # stage1 + (stage2 -> stage3) de la rama critica
    if spec["kind"] == "multistage_sequential":
        return 1 + 2 * num_meanings
    return 1


def _check_against_baseline(fresh, baseline_doc, fixture, threshold, sleep_overhead_s):
    """Devuelve la lista de violaciones (vacia = gate verde).

    Compara la latencia relativa MEDIDA de la corrida fresca contra la
    ESPERADA versionada en el baseline (analitica, independiente de la
    maquina), ajustada por el overhead de sleep calibrado en esta maquina.
    """
    violations = []
    baseline = baseline_doc["strategies"]
    num_meanings = fixture["num_meanings"]

    def adjusted_expected(key):
        expected_p50 = baseline[key].get("expected_p50_s")
        if expected_p50 is None:
            return None
        chained = _chained_sleeps(fixture["strategies"][key], num_meanings)
        return expected_p50 + chained * sleep_overhead_s

    baseline_adjusted = (
        adjusted_expected(BASELINE_STRATEGY) if BASELINE_STRATEGY in baseline else None
    )
    for key, summary in fresh.items():
        if summary["failures"]:
            violations.append(
                f"{key}: {summary['failures']} corrida(s) invalida(s) en replay "
                f"({summary['failure_messages']})"
            )
            continue
        if key not in baseline:
            violations.append(f"{key}: sin baseline en results.json (regenerar baseline)")
            continue
        fresh_rel = summary["relative_p50_vs_monolithic"]
        adjusted = adjusted_expected(key)
        if fresh_rel is None or adjusted is None or not baseline_adjusted:
            violations.append(f"{key}: latencia relativa no computable (p50 ausente)")
            continue
        expected_rel = adjusted / baseline_adjusted
        upper = expected_rel * (1 + threshold)
        lower = expected_rel / (1 + threshold)
        if not (lower <= fresh_rel <= upper):
            violations.append(
                f"{key}: latencia relativa p50 medida {fresh_rel:.3f} fuera de "
                f"[{lower:.3f}, {upper:.3f}] (esperada {expected_rel:.3f} "
                f"ajustada por overhead de sleep {sleep_overhead_s * 1000:.1f}ms, "
                f"umbral +/-{threshold:.0%})"
            )
    for key in baseline:
        if key not in fresh:
            violations.append(f"{key}: presente en baseline pero no corrio en el replay")
    return violations


def _print_table(summaries):
    print(f"\n{'estrategia':<22} {'n':>3} {'p50':>8} {'p95':>8} {'p99':>8} {'rel':>6} {'fail':>4}")
    for key, s in summaries.items():
        rel = s["relative_p50_vs_monolithic"]
        print(
            f"{key:<22} {s['n']:>3} "
            f"{s['p50_s']:>7.3f}s {s['p95_s']:>7.3f}s {s['p99_s']:>7.3f}s "
            f"{rel if rel is None else format(rel, '.2f'):>6} {s['failures']:>4}"
        )


def main():
    parser = argparse.ArgumentParser(description="Replay benchmark harness (offline)")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="Desvio relativo tolerado por estrategia en --check (default 0.25 = 25%%)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compara contra benchmarks/results.json y falla si hay regresion relativa",
    )
    parser.add_argument(
        "--output",
        default=str(RESULTS_PATH),
        help="Destino del results.json (solo sin --check)",
    )
    args = parser.parse_args()

    fixture = load_fixture()
    print(
        f"Replay fixture v{fixture['fixture_version']} | time_scale={fixture['time_scale']} | "
        f"{len(fixture['strategies'])} estrategias x {args.iterations} iteraciones"
    )

    summaries = asyncio.run(_run_all(fixture, args.iterations, args.timeout))
    _attach_relatives(summaries)
    expected = _expected_stats(fixture, args.iterations)
    for key, stats in expected.items():
        if key in summaries:
            summaries[key].update(stats)
    _print_table(summaries)

    if args.check:
        if not RESULTS_PATH.exists():
            raise SystemExit(f"No hay baseline en {RESULTS_PATH}; corre sin --check primero")
        with open(RESULTS_PATH, encoding="utf-8") as handle:
            baseline_doc = json.load(handle)
        if baseline_doc.get("iterations") != args.iterations:
            print(
                f"AVISO: baseline generado con iterations={baseline_doc.get('iterations')}, "
                f"este check corre con {args.iterations}; los percentiles pueden diferir."
            )
        sleep_overhead_s = asyncio.run(_calibrate_sleep_overhead())
        print(f"Overhead de sleep calibrado: {sleep_overhead_s * 1000:.1f}ms por llamada")
        violations = _check_against_baseline(
            summaries, baseline_doc, fixture, args.threshold, sleep_overhead_s
        )
        if violations:
            print("\nGATE ROJO: latencia relativa fuera del umbral o corridas invalidas:")
            for violation in violations:
                print(f"  - {violation}")
            raise SystemExit(1)
        print(f"\nGATE VERDE: {len(summaries)}/{len(summaries)} estrategias dentro del umbral")
        return

    document = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "replay",
        "fixture_version": fixture["fixture_version"],
        "time_scale": fixture["time_scale"],
        "iterations": args.iterations,
        "baseline_strategy": BASELINE_STRATEGY,
        "note": (
            "Percentiles de un replay deterministico de corridas reales grabadas "
            "(ver benchmarks/fixtures/). NO son mediciones frescas contra la API "
            "viva. El gate (--check) compara la latencia RELATIVA medida contra "
            "expected_relative_p50 (analitico, independiente de la maquina); los "
            "campos p50/p95/p99_s medidos incluyen el overhead del event loop "
            "del runner que genero este archivo."
        ),
        "strategies": summaries,
    }
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"\nBaseline escrito en {output_path}")


if __name__ == "__main__":
    main()
