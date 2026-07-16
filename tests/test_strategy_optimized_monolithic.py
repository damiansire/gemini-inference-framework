"""Test por estrategia: optimized_monolithic (prompt corto few-shot, temperatura 0)."""

import asyncio

from google.genai import errors as genai_errors

from strategies.optimized_monolithic.runner import run_optimized
from strategies.output_validation import FULL_LEVELS
from tests.replay_support import FailingProvider, assert_success_contract


def test_contrato_comun_y_salida_valida(replay_provider):
    replay_provider.begin_run("optimized_monolithic", 0)
    result = asyncio.run(run_optimized("hana", salt="s1", timeout=30))
    assert_success_contract(result, FULL_LEVELS)


def test_api_error_es_fallo_esperado_no_excepcion(provider_sandbox):
    provider_sandbox(FailingProvider(genai_errors.APIError(429, {"error": {"message": "rate"}})))
    result = asyncio.run(run_optimized("hana", timeout=5))
    assert result["success"] is False
    assert result["error"]
