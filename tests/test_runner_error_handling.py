"""Tests del estrechamiento de excepciones en los leaf runners (H3 / Fase 1).

Antes, cada leaf runner hacia ``except Exception as e`` y aplanaba CUALQUIER
fallo a ``{"success": False, "error": str(e)}``. Eso contaminaba la tasa de
fallo del benchmark: un GOOGLE_API_KEY ausente, un KeyError o un bug de config
se contaban como un "fallo de la estrategia", indistinguibles de un mal output
del modelo.

Ahora los runners solo tragan errores ESPERADOS de inferencia (timeout / error
de la API de Gemini). Los inesperados (config / programacion) se dejan propagar
para que el orquestador los loguee con traceback en vez de contarlos como un
fallo de inferencia.
"""

import asyncio

import pytest
from google.genai import errors as genai_errors

from strategies import utils
from strategies.monolithic.runner import run_monolithic
from strategies.thinking_budget.runner import run_thinking_budget


def _make_api_error(code=429):
    return genai_errors.APIError(code, {"error": {"message": "rate limited"}})


def _patch_stream(monkeypatch, side_effect):
    """Reemplaza generate_content_stream por un fake async que lanza/retorna."""

    async def fake_stream(*args, **kwargs):
        if isinstance(side_effect, Exception):
            raise side_effect
        if callable(side_effect):
            return side_effect()
        return side_effect

    # Los runners importan la funcion por nombre desde ..utils, asi que hay que
    # parchear el binding en cada modulo de runner ademas del de utils.
    monkeypatch.setattr(utils, "generate_content_stream", fake_stream)
    monkeypatch.setattr(
        "strategies.monolithic.runner.generate_content_stream", fake_stream
    )
    monkeypatch.setattr(
        "strategies.thinking_budget.runner.generate_content_stream", fake_stream
    )


# --- Errores ESPERADOS: se tragan y se reportan como run fallido --------------


def test_api_error_se_cuenta_como_fallo(monkeypatch):
    _patch_stream(monkeypatch, _make_api_error(429))
    result = asyncio.run(run_monolithic("hana"))
    assert result["success"] is False
    assert result["timed_out"] is False
    assert result["error"]  # mensaje accionable, no vacio


def test_timeout_se_marca_timed_out(monkeypatch):
    _patch_stream(monkeypatch, asyncio.TimeoutError())
    result = asyncio.run(run_monolithic("hana"))
    assert result["success"] is False
    assert result["timed_out"] is True


def test_thinking_budget_conserva_thinking_level_en_fallo(monkeypatch):
    _patch_stream(monkeypatch, _make_api_error(500))
    result = asyncio.run(run_thinking_budget("hana", thinking_level="LOW"))
    assert result["success"] is False
    # El campo extra por estrategia se preserva en el dict de fallo.
    assert result["thinking_level"] == "LOW"


# --- Errores INESPERADOS: NO se tragan, deben propagar ------------------------


def test_error_de_config_propaga_no_se_aplana(monkeypatch):
    """Un fallo de config (p. ej. KeyError) NO debe contarse como fallo de
    inferencia: tiene que propagar para que el orquestador lo loguee."""
    _patch_stream(monkeypatch, KeyError("GOOGLE_API_KEY"))
    with pytest.raises(KeyError):
        asyncio.run(run_monolithic("hana"))


def test_value_error_de_setup_propaga(monkeypatch):
    """Un ValueError tipico de un cliente mal configurado tampoco se aplana."""
    _patch_stream(monkeypatch, ValueError("Missing key: pass api_key"))
    with pytest.raises(ValueError):
        asyncio.run(run_monolithic("hana"))
