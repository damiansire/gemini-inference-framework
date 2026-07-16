"""Test por estrategia: monolithic (baseline sin schema, camino streaming)."""

import asyncio

from google.genai import errors as genai_errors

from strategies.monolithic.runner import run_monolithic
from strategies.output_validation import FULL_LEVELS
from tests.replay_support import FailingProvider, assert_success_contract


def test_contrato_comun_y_salida_valida(replay_provider):
    replay_provider.begin_run("monolithic", 0)
    result = asyncio.run(run_monolithic("hana", salt="s1", timeout=30))
    assert_success_contract(result, FULL_LEVELS)
    # Camino streaming: el runner reporta el texto crudo del stream.
    assert isinstance(result["text_output"], str)


def test_api_error_es_fallo_esperado_no_excepcion(provider_sandbox):
    provider_sandbox(FailingProvider(genai_errors.APIError(429, {"error": {"message": "rate"}})))
    result = asyncio.run(run_monolithic("hana", timeout=5))
    assert result["success"] is False
    assert result["timed_out"] is False
    assert result["error"]
