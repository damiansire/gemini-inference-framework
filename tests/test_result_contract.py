"""Tests de los helpers unicos del contrato de dict plano (strategies/utils.py).

El contrato comun (AGENTS.md) vivia en prosa y se armaba a mano en 8 sitios,
con 3 variantes divergentes del dict de fallo. Ahora ``inference_success_result``
e ``inference_failure_result`` son el UNICO lugar donde se arma la forma; esta
suite la fija para que un drift futuro rompa un test, no un reporte.
"""

import asyncio

from strategies.utils import (
    PRO_MODEL,
    estimate_cost,
    inference_failure_result,
    inference_success_result,
    success_result_from_payload,
)
from tests.replay_support import CONTRACT_KEYS


def _payload(text="salida", parsed=None):
    class _Usage:
        prompt_token_count = 100
        candidates_token_count = 40
        thoughts_token_count = 10
        total_token_count = 150

    return {
        "text": text,
        "parsed": parsed,
        "usage": _Usage(),
        "duration": 2.5,
        "ttft": 0.4,
    }


def test_success_result_cubre_todas_las_claves_del_contrato():
    result = success_result_from_payload(_payload())
    missing = [key for key in CONTRACT_KEYS if key not in result]
    assert missing == []
    assert result["success"] is True
    assert result["timed_out"] is False


def test_failure_result_cubre_el_contrato_de_fallo():
    result = inference_failure_result(asyncio.TimeoutError())
    # En fallo el contrato pide las claves numericas + error; text_output no aplica.
    missing = [key for key in CONTRACT_KEYS if key != "text_output" and key not in result]
    assert missing == []
    assert result["success"] is False
    assert result["timed_out"] is True
    assert result["error"]


def test_success_y_failure_comparten_la_base_del_shape():
    # Si alguien agrega un campo base a un helper y no al otro, el consumidor
    # (summarize_metrics / _normalize_result) ve dicts asimetricos.
    success_keys = set(success_result_from_payload(_payload()))
    failure_keys = set(inference_failure_result(ValueError("boom")))
    assert success_keys - failure_keys == {"text_output"}
    assert failure_keys - success_keys == {"error"}


def test_from_payload_mapea_usage_y_costo():
    result = success_result_from_payload(_payload())
    assert result["prompt_tokens"] == 100
    assert result["candidate_tokens"] == 40
    assert result["thought_tokens"] == 10
    assert result["total_tokens"] == 150
    assert result["cost"] == estimate_cost(100, 40 + 10)
    assert result["duration"] == 2.5
    assert result["ttft"] == 0.4
    assert result["text_output"] == "salida"


def test_from_payload_respeta_modelo_y_override_de_text_output():
    parsed = [{"englishDefinition": "a tap"}]
    result = success_result_from_payload(
        _payload(parsed=parsed), model=PRO_MODEL, text_output=parsed
    )
    assert result["cost"] == estimate_cost(100, 50, PRO_MODEL)
    assert result["text_output"] is parsed

    # Override None (p. ej. response["parsed"] ausente) cae a payload["text"].
    fallback = success_result_from_payload(_payload(), text_output=None)
    assert fallback["text_output"] == "salida"


def test_campos_extra_por_estrategia_pasan_en_ambos_helpers():
    ok = success_result_from_payload(_payload(), thinking_level="LOW")
    fail = inference_failure_result(asyncio.TimeoutError(), thinking_level="LOW")
    assert ok["thinking_level"] == "LOW"
    assert fail["thinking_level"] == "LOW"


def test_success_result_directo_arma_el_shape_completo():
    result = inference_success_result(
        duration=1.0,
        ttft=0.1,
        prompt_tokens=1,
        candidate_tokens=2,
        thought_tokens=3,
        total_tokens=6,
        cost=0.001,
        text_output=[],
    )
    missing = [key for key in CONTRACT_KEYS if key not in result]
    assert missing == []
