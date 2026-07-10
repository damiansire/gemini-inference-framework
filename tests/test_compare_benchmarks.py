"""Tests del cableado que decide que numero se publica (compare_benchmarks.py).

Hasta ahora esta capa (el "quality gate" real: que corrida cuenta como exitosa,
que estrategia se corona "la mas rapida totalmente valida") no tenia ningun
test, pese a ser exactamente lo que un benchmark de latencia vende como su
producto. Hallazgo de /fragua evaluar 2026-07-10 (veredicto REJECT).
"""

from compare_benchmarks import _pick_best_quality_speed


def _summary(successful_runs=1, valid_output_rate=1.0, avg_duration=1.0):
    return {
        "successful_runs": successful_runs,
        "valid_output_rate": valid_output_rate,
        "avg_duration": avg_duration,
    }


# --- _pick_best_quality_speed: "fully valid" debe significar FULL_LEVELS ------


def test_excluye_estrategia_de_niveles_parciales_aunque_sea_mas_rapida():
    # lazy_optimized (LAZY_LEVELS) es mas rapida y tiene valid_output_rate 1.0
    # relativo a SU PROPIO contrato parcial (A1-B1) -- no debe ganar "fully valid".
    summaries = {
        "cascade": _summary(avg_duration=17.2),
        "lazy_optimized": _summary(avg_duration=5.0),
    }
    key, _ = _pick_best_quality_speed(summaries)
    assert key == "cascade"


def test_elige_la_mas_rapida_entre_full_level_strategies():
    summaries = {
        "cascade": _summary(avg_duration=17.2),
        "monolithic": _summary(avg_duration=22.0),
        "lazy_optimized": _summary(avg_duration=3.0),
    }
    key, _ = _pick_best_quality_speed(summaries)
    assert key == "cascade"


def test_devuelve_none_si_solo_hay_estrategias_parciales():
    summaries = {"lazy_optimized": _summary(avg_duration=5.0)}
    assert _pick_best_quality_speed(summaries) is None


def test_devuelve_none_si_ninguna_corrida_exitosa():
    summaries = {"cascade": _summary(successful_runs=0)}
    assert _pick_best_quality_speed(summaries) is None


def test_devuelve_none_si_valid_output_rate_bajo():
    summaries = {"cascade": _summary(valid_output_rate=0.5)}
    assert _pick_best_quality_speed(summaries) is None
