"""Test por estrategia: lazy_optimized (contrato PARCIAL, solo A1-B1)."""

import asyncio

from google.genai import errors as genai_errors

from strategies.lazy_optimized.runner import run_lazy_optimized
from strategies.output_validation import FULL_LEVELS, LAZY_LEVELS, validate_dictionary_output
from tests.replay_support import FailingProvider, assert_success_contract


def test_contrato_comun_y_salida_valida_contra_lazy_levels(replay_provider):
    replay_provider.begin_run("lazy_optimized", 0)
    result = asyncio.run(run_lazy_optimized("hana", salt="s1", timeout=30))
    assert_success_contract(result, LAZY_LEVELS)


def test_su_salida_parcial_no_pasa_por_full_levels(replay_provider):
    # Documenta el borde del contrato: lo que lazy_optimized produce es valido
    # SOLO contra LAZY_LEVELS; contra FULL_LEVELS debe fallar (por eso
    # _pick_best_quality_speed la excluye de "fully valid").
    replay_provider.begin_run("lazy_optimized", 0)
    result = asyncio.run(run_lazy_optimized("hana", timeout=30))
    validation = validate_dictionary_output(result["text_output"], expected_levels=FULL_LEVELS)
    assert validation["ok"] is False


def test_api_error_es_fallo_esperado_no_excepcion(provider_sandbox):
    provider_sandbox(FailingProvider(genai_errors.APIError(503, {"error": {"message": "down"}})))
    result = asyncio.run(run_lazy_optimized("hana", timeout=5))
    assert result["success"] is False
    assert result["error"]
