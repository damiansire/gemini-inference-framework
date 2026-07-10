"""Tests del cableado que decide que numero se publica (compare_benchmarks.py).

Hasta ahora esta capa (el "quality gate" real: que corrida cuenta como exitosa,
que estrategia se corona "la mas rapida totalmente valida") no tenia ningun
test, pese a ser exactamente lo que un benchmark de latencia vende como su
producto. Hallazgo de /fragua evaluar 2026-07-10 (veredicto REJECT).
"""

import asyncio
import json

import pytest

from compare_benchmarks import _normalize_result, _pick_best_quality_speed, main, summarize_metrics


def _valid_payload():
    return json.dumps(
        {
            "meanings": [
                {
                    "englishDefinition": "a tap or faucet",
                    "definiendum": "hana",
                    "synonyms": [],
                    "antonyms": [],
                    "examples": [
                        {"sourceFi": f"esimerkki {level}", "level": level}
                        for level in ("a1", "a2", "b1", "b2", "c1", "c2")
                    ],
                }
            ]
        }
    )


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


# --- _normalize_result: el punto unico donde success/output_valid se decide ---


def test_normalize_result_api_ok_y_output_valido():
    result = {"success": True, "duration": 1.5, "text_output": _valid_payload()}
    normalized = _normalize_result("monolithic", result)
    assert normalized["api_success"] is True
    assert normalized["output_valid"] is True
    assert normalized["success"] is True
    assert normalized["validation_errors"] == []
    assert isinstance(normalized["text_output"], (dict, list))  # normalizado, no el string crudo


def test_normalize_result_api_ok_pero_output_invalido_flipea_success():
    result = {"success": True, "duration": 1.5, "text_output": "not json"}
    normalized = _normalize_result("monolithic", result)
    assert normalized["api_success"] is True
    assert normalized["output_valid"] is False
    # el flip es el corazon del quality gate: un output invalido NUNCA cuenta
    # como corrida exitosa aunque la llamada a la API haya terminado bien.
    assert normalized["success"] is False
    assert normalized["error"]


def test_normalize_result_api_fail_no_corre_el_validador():
    result = {"success": False, "error": "timeout"}
    normalized = _normalize_result("monolithic", result)
    assert normalized["api_success"] is False
    assert normalized["output_valid"] is False
    assert normalized["validation_errors"] == []
    assert normalized["error"] == "timeout"


def test_normalize_result_respeta_expected_levels_por_estrategia():
    # lazy_optimized solo promete LAZY_LEVELS (A1-B1): un payload que SOLO
    # cubre esos niveles debe validar para esa estrategia...
    lazy_payload = json.dumps(
        {
            "meanings": [
                {
                    "englishDefinition": "a tap",
                    "definiendum": "hana",
                    "examples": [
                        {"sourceFi": f"esimerkki {level}", "level": level}
                        for level in ("a1", "a2", "b1")
                    ],
                }
            ]
        }
    )
    normalized = _normalize_result("lazy_optimized", {"success": True, "text_output": lazy_payload})
    assert normalized["output_valid"] is True

    # ...pero el mismo payload parcial NO alcanza para una estrategia FULL_LEVELS.
    normalized_full = _normalize_result(
        "monolithic", {"success": True, "text_output": lazy_payload}
    )
    assert normalized_full["output_valid"] is False
    assert normalized_full["success"] is False


def test_normalize_result_preserva_campos_extra_y_raw_text_output():
    result = {
        "success": True,
        "text_output": _valid_payload(),
        "thinking_level": "LOW",  # campo extra que no esta en el shape base
    }
    normalized = _normalize_result("monolithic", result)
    assert normalized["thinking_level"] == "LOW"
    assert normalized["raw_text_output"] == result["text_output"]


# --- summarize_metrics: produce las tasas del leaderboard ---------------------


def _run(success=True, api_success=None, output_valid=None, timed_out=False, duration=1.0):
    return {
        "success": success,
        "api_success": api_success if api_success is not None else success,
        "output_valid": output_valid if output_valid is not None else success,
        "timed_out": timed_out,
        "duration": duration,
        "ttft": 0.1,
        "total_tokens": 100,
        "thought_tokens": 10,
        "cost": 0.001,
    }


def test_summarize_metrics_runs_vacio_no_divide_por_cero():
    summary = summarize_metrics([])
    assert summary["valid_output_rate"] == 0
    assert summary["api_success_rate"] == 0
    assert summary["failure_rate"] == 0
    assert summary["total_runs"] == 0


def test_summarize_metrics_un_solo_run_std_es_cero():
    summary = summarize_metrics([_run()])
    assert summary["std_duration"] == 0
    assert summary["successful_runs"] == 1
    assert summary["valid_output_rate"] == 1.0


def test_summarize_metrics_mix_valido_api_only_y_timeout():
    runs = [
        _run(success=True),
        _run(success=False, api_success=True, output_valid=False),  # api ok, validacion fallo
        _run(success=False, api_success=False, timed_out=True),  # timeout puro
    ]
    summary = summarize_metrics(runs)
    assert summary["successful_runs"] == 1
    assert summary["api_successful_runs"] == 2
    assert summary["validation_failed_runs"] == 1
    assert summary["timeout_runs"] == 1
    assert summary["failure_rate"] == 2 / 3
    assert summary["valid_output_rate"] == 1 / 3


# --- main(): preflight fail-fast si falta GOOGLE_API_KEY ----------------------


def test_main_aborta_de_una_si_falta_google_api_key(monkeypatch, capsys):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["compare_benchmarks.py", "--words", "hana"])
    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(main())
    assert exc_info.value.code == 1
    assert "GOOGLE_API_KEY" in capsys.readouterr().out
