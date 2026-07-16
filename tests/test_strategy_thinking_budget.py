"""Test por estrategia: thinking_budget (monolithic con thinking_level=LOW)."""

import asyncio

from google.genai import errors as genai_errors

from strategies.output_validation import FULL_LEVELS
from strategies.thinking_budget.runner import run_thinking_budget
from tests.replay_support import FailingProvider, assert_success_contract


def test_contrato_comun_y_salida_valida(replay_provider):
    replay_provider.begin_run("thinking_budget", 0)
    result = asyncio.run(run_thinking_budget("hana", salt="s1", timeout=30))
    assert_success_contract(result, FULL_LEVELS)
    # Campo extra por estrategia: se preserva tambien en el exito, no solo en
    # el fallo (el fallo ya lo cubre test_runner_error_handling).
    assert result["thinking_level"] == "LOW"


def test_api_error_preserva_thinking_level(provider_sandbox):
    provider_sandbox(FailingProvider(genai_errors.APIError(429, {"error": {"message": "rate"}})))
    result = asyncio.run(run_thinking_budget("hana", thinking_level="MINIMAL", timeout=5))
    assert result["success"] is False
    assert result["thinking_level"] == "MINIMAL"
