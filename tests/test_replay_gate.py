"""Tests del comparador del gate de replay (benchmarks/run.py).

El gate nightly (bench.yml) depende de ``_check_against_baseline``: si su
logica se rompe en silencio, el gate queda verde para siempre. Aca se cubren
las dos direcciones del umbral (regresion Y mejora sospechosa), el caso de
corridas invalidas y el de estrategias faltantes, sin dormir ni correr el
harness completo.
"""

from benchmarks.run import (
    BASELINE_STRATEGY,
    _check_against_baseline,
    _expected_stats,
    percentile,
)

_FIXTURE = {
    "time_scale": 0.05,
    "num_meanings": 3,
    "strategies": {
        BASELINE_STRATEGY: {"kind": "single_stream", "durations_s": [20.0, 22.0, 24.0]},
        "cascade": {"kind": "multistage_parallel", "durations_s": [15.0, 16.0, 17.0]},
        "pipeline": {"kind": "multistage_sequential", "durations_s": [120.0, 140.0, 160.0]},
    },
}


def _summary(p50, failures=0):
    return {
        "p50_s": p50,
        "failures": failures,
        "failure_messages": ["boom"] if failures else [],
        "relative_p50_vs_monolithic": None,  # se setea abajo
    }


def _fresh(mono_p50, cascade_p50, pipeline_p50):
    fresh = {
        BASELINE_STRATEGY: _summary(mono_p50),
        "cascade": _summary(cascade_p50),
        "pipeline": _summary(pipeline_p50),
    }
    for summary in fresh.values():
        summary["relative_p50_vs_monolithic"] = summary["p50_s"] / mono_p50
    return fresh


def _baseline_doc():
    return {"strategies": _expected_stats(_FIXTURE, iterations=3)}


def test_percentile_interpolacion_basica():
    values = [1.0, 2.0, 3.0, 4.0]
    assert percentile(values, 50) == 2.5
    assert percentile(values, 0) == 1.0
    assert percentile(values, 100) == 4.0
    assert percentile([], 50) is None
    assert percentile([7.0], 99) == 7.0


def test_expected_stats_escala_y_relativos():
    expected = _expected_stats(_FIXTURE, iterations=3)
    # p50 de [20,22,24] * 0.05 = 1.1; relativo del baseline = 1.0 exacto.
    assert expected[BASELINE_STRATEGY]["expected_p50_s"] == 1.1
    assert expected[BASELINE_STRATEGY]["expected_relative_p50"] == 1.0
    assert expected["cascade"]["expected_relative_p50"] < 1.0


def test_gate_verde_cuando_lo_medido_coincide_con_lo_esperado():
    # Medidos == esperados analiticos (overhead 0): cero violaciones.
    fresh = _fresh(mono_p50=1.1, cascade_p50=0.8, pipeline_p50=7.0)
    violations = _check_against_baseline(
        fresh, _baseline_doc(), _FIXTURE, threshold=0.25, sleep_overhead_s=0.0
    )
    assert violations == []


def test_gate_rojo_si_una_estrategia_regresa_relativa():
    # cascade tarda 2x lo esperado (como si el gather se hubiera serializado).
    fresh = _fresh(mono_p50=1.1, cascade_p50=1.6, pipeline_p50=7.0)
    violations = _check_against_baseline(
        fresh, _baseline_doc(), _FIXTURE, threshold=0.25, sleep_overhead_s=0.0
    )
    assert any(v.startswith("cascade:") for v in violations)


def test_gate_rojo_si_una_estrategia_mejora_sospechosamente():
    # pipeline "gratis" 3x mas rapida: en replay eso significa que se
    # perdieron llamadas/sleeps, no que el codigo mejoro. Debe fallar tambien.
    fresh = _fresh(mono_p50=1.1, cascade_p50=0.8, pipeline_p50=2.3)
    violations = _check_against_baseline(
        fresh, _baseline_doc(), _FIXTURE, threshold=0.25, sleep_overhead_s=0.0
    )
    assert any(v.startswith("pipeline:") for v in violations)


def test_gate_rojo_si_hay_corridas_invalidas():
    fresh = _fresh(mono_p50=1.1, cascade_p50=0.8, pipeline_p50=7.0)
    fresh["cascade"]["failures"] = 2
    fresh["cascade"]["failure_messages"] = ["Output validation failed"]
    violations = _check_against_baseline(
        fresh, _baseline_doc(), _FIXTURE, threshold=0.25, sleep_overhead_s=0.0
    )
    assert any("invalida" in v for v in violations)


def test_gate_rojo_si_falta_una_estrategia_del_baseline():
    fresh = _fresh(mono_p50=1.1, cascade_p50=0.8, pipeline_p50=7.0)
    del fresh["pipeline"]
    violations = _check_against_baseline(
        fresh, _baseline_doc(), _FIXTURE, threshold=0.25, sleep_overhead_s=0.0
    )
    assert any("pipeline" in v and "no corrio" in v for v in violations)


def test_calibracion_compensa_overhead_por_sleeps_encadenados():
    # Con overhead real de 100ms por sleep: single suma 1, cascade 3,
    # pipeline 1+2*M=7. Un medido inflado exactamente asi debe pasar.
    overhead = 0.1
    fresh = _fresh(
        mono_p50=1.1 + 1 * overhead,
        cascade_p50=0.8 + 3 * overhead,
        pipeline_p50=7.0 + 7 * overhead,
    )
    violations = _check_against_baseline(
        fresh, _baseline_doc(), _FIXTURE, threshold=0.25, sleep_overhead_s=overhead
    )
    assert violations == []
