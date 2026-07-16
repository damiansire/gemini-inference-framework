"""Test por estrategia: monolithic_schema (response_schema estricto, non-streaming)."""

import asyncio

from google.genai import errors as genai_errors

from strategies.monolithic.runner import run_monolithic_schema
from strategies.output_validation import FULL_LEVELS
from tests.replay_support import FailingProvider, assert_success_contract


def test_contrato_comun_y_salida_valida(replay_provider):
    replay_provider.begin_run("monolithic_schema", 0)
    result = asyncio.run(run_monolithic_schema("hana", salt="s1", timeout=30))
    assert_success_contract(result, FULL_LEVELS)
    # Con response_schema el SDK entrega `.parsed`: el runner debe preferirlo
    # al texto crudo (payload estructurado, no string).
    assert isinstance(result["text_output"], (dict, list))


def test_api_error_es_fallo_esperado_no_excepcion(provider_sandbox):
    provider_sandbox(FailingProvider(genai_errors.APIError(500, {"error": {"message": "boom"}})))
    result = asyncio.run(run_monolithic_schema("hana", timeout=5))
    assert result["success"] is False
    assert result["timed_out"] is False
    assert result["error"]
