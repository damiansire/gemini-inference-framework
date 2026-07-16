"""Test por estrategia: cascade (multi-etapa paralela, version registrada).

Se prueba la version ENVUELTA (``run_cascade_strategy`` en
``scripts/compare_benchmarks.py``), que es la registrada en ``STRATEGIES`` y la
que promete el contrato comun de dict plano; la base ``run_cascade`` devuelve
``(result, metrics)`` y no se registra directa (ver AGENTS.md).
"""

import asyncio

from google.genai import errors as genai_errors

from scripts.compare_benchmarks import run_cascade_strategy
from strategies.output_validation import FULL_LEVELS
from tests.replay_support import FailingProvider, assert_success_contract


def test_contrato_comun_y_salida_valida(replay_provider):
    replay_provider.begin_run("cascade", 0)
    result = asyncio.run(run_cascade_strategy("hana", salt="s1", timeout=30))
    assert_success_contract(result, FULL_LEVELS)
    # Estructura de llamadas del fan-out: 1 (stage1) + 2 por acepcion
    # (stage2 + stage3). Si esto cambia, cambio la orquestacion que el
    # benchmark dice medir.
    num_meanings = replay_provider.fixture["num_meanings"]
    assert replay_provider.total_calls == 1 + 2 * num_meanings


def test_api_error_es_fallo_esperado_no_excepcion(provider_sandbox):
    provider_sandbox(FailingProvider(genai_errors.APIError(429, {"error": {"message": "rate"}})))
    result = asyncio.run(run_cascade_strategy("hana", timeout=5))
    assert result["success"] is False
    assert result["timed_out"] is False
    assert result["error"]


def test_timeout_se_marca_timed_out(provider_sandbox):
    provider_sandbox(FailingProvider(asyncio.TimeoutError()))
    result = asyncio.run(run_cascade_strategy("hana", timeout=5))
    assert result["success"] is False
    assert result["timed_out"] is True
