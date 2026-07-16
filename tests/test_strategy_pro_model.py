"""Test por estrategia: pro_model (misma tarea sobre Gemini Pro)."""

import asyncio

from google.genai import errors as genai_errors

from strategies.output_validation import FULL_LEVELS
from strategies.pro_model.runner import run_pro_model
from strategies.utils import PRO_MODEL
from tests.replay_support import FailingProvider, assert_success_contract


def test_contrato_comun_y_salida_valida(replay_provider):
    replay_provider.begin_run("pro_model", 0)
    result = asyncio.run(run_pro_model("hana", salt="s1", timeout=30))
    assert_success_contract(result, FULL_LEVELS)
    # La razon de ser de la estrategia: debe pegarle al modelo Pro, no a Flash
    # (si esto regresa, el benchmark compara dos veces el mismo modelo).
    assert replay_provider.models_seen == [PRO_MODEL]


def test_api_error_es_fallo_esperado_no_excepcion(provider_sandbox):
    provider_sandbox(FailingProvider(genai_errors.APIError(429, {"error": {"message": "rate"}})))
    result = asyncio.run(run_pro_model("hana", timeout=5))
    assert result["success"] is False
    assert result["error"]
