"""Test por estrategia: pipeline (multi-etapa secuencial, version registrada).

Igual que cascade, se prueba la version ENVUELTA (``run_pipeline_strategy``),
que es la registrada en ``STRATEGIES`` con el contrato comun de dict plano.
"""

import asyncio

import pytest
from google.genai import errors as genai_errors

from scripts.compare_benchmarks import run_pipeline_strategy
from strategies.output_validation import FULL_LEVELS
from tests.replay_support import FailingProvider, assert_success_contract


def test_contrato_comun_y_salida_valida(replay_provider):
    replay_provider.begin_run("pipeline", 0)
    result = asyncio.run(run_pipeline_strategy("hana", salt="s1", timeout=30))
    assert_success_contract(result, FULL_LEVELS)
    # Misma estructura de llamadas que cascade (1 + 2M); la diferencia entre
    # ambas es secuencial vs paralelo, no el numero de llamadas.
    num_meanings = replay_provider.fixture["num_meanings"]
    assert replay_provider.total_calls == 1 + 2 * num_meanings


def test_api_error_es_fallo_esperado_no_excepcion(provider_sandbox):
    provider_sandbox(FailingProvider(genai_errors.APIError(500, {"error": {"message": "boom"}})))
    result = asyncio.run(run_pipeline_strategy("hana", timeout=5))
    assert result["success"] is False
    assert result["timed_out"] is False
    assert result["error"]


def test_timeout_se_marca_timed_out(provider_sandbox):
    provider_sandbox(FailingProvider(asyncio.TimeoutError()))
    result = asyncio.run(run_pipeline_strategy("hana", timeout=5))
    assert result["success"] is False
    assert result["timed_out"] is True


def test_bug_de_programacion_propaga_no_se_aplana(provider_sandbox):
    """Un error INESPERADO (bug de config/programacion) NO cuenta como fallo de
    la estrategia: propaga, igual que en los leaf runners (doctrina
    EXPECTED_INFERENCE_ERRORS en strategies/utils.py)."""
    provider_sandbox(FailingProvider(KeyError("GOOGLE_API_KEY")))
    with pytest.raises(KeyError):
        asyncio.run(run_pipeline_strategy("hana", timeout=5))
