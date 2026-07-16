"""Prueba de pluggability de la capa de proveedor (gif-5, Fase 3).

`InferenceProvider` (strategies/providers.py) es un `Protocol` runtime-checkable
pensado para que enchufar un backend distinto de Gemini sea inyectar otro
adapter via `utils.set_provider`, sin tocar los runners. Este archivo prueba esa
promesa con un provider MOCK que representa la FORMA de un segundo backend
(otro SDK, otro vendor) -- no pega a ninguna API paga real.

Lo que NO cubre este test: una corrida real contra un segundo proveedor pago
(OpenAI/Anthropic/etc.). Eso queda pendiente de una segunda API key; ver
AGENTS.md / README para el comando exacto que correria esa corrida.
"""

import asyncio

import pytest

from prompts import TEST_WORDS
from strategies.monolithic.runner import run_monolithic_schema
from strategies.output_validation import FULL_LEVELS, validate_dictionary_output
from strategies.providers import InferenceProvider
from strategies.utils import get_provider, reset_inference_semaphore, set_provider


class _FakeUsage:
    """Forma minima de ``usage_metadata`` que ``_extract_usage`` necesita."""

    def __init__(self):
        self.prompt_token_count = 42
        self.candidates_token_count = 84
        self.thoughts_token_count = 0
        self.total_token_count = 126


class _FakeResponse:
    def __init__(self, parsed):
        self.parsed = parsed
        self.text = ""
        self.usage_metadata = _FakeUsage()


def _entry(level):
    return {"sourceFi": f"lause {level}", "spokenFi": None, "level": level}


def _valid_payload():
    """Un payload que pasa validate_dictionary_output con FULL_LEVELS."""
    return [
        {
            "englishDefinition": "a bridge",
            "examples": [_entry(lvl) for lvl in FULL_LEVELS],
            "synonyms": [],
            "antonyms": [],
            "definiendum": {"en": "bridge"},
        }
    ]


class SecondBackendProvider:
    """Adapter con la FORMA de un segundo backend (no Gemini).

    No hereda de nada -- la conformidad con ``InferenceProvider`` es
    estructural (``Protocol``), que es justamente lo que este test verifica: si
    hiciera falta una base class compartida, "enchufar otro proveedor sin
    reescribir la estrategia" seria falso.
    """

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    async def generate_content(self, *, model, contents, config):
        self.calls += 1
        await asyncio.sleep(0)  # keep it a real coroutine, no red real
        return _FakeResponse(self._payload)

    async def generate_content_stream(self, *, model, contents, config):  # pragma: no cover
        raise NotImplementedError("este mock solo ejercita el camino non-streaming")


@pytest.fixture(autouse=True)
def _restore_provider():
    original = get_provider()
    yield
    set_provider(original)
    reset_inference_semaphore()


def test_second_backend_provider_satisface_el_protocolo_en_runtime():
    provider = SecondBackendProvider(_valid_payload())
    assert isinstance(provider, InferenceProvider)


def test_strategy_corre_end_to_end_contra_un_segundo_backend_mock():
    """run_monolithic_schema (generate_content_sync, non-streaming) no debe
    saber ni importarle que el provider inyectado no es GeminiProvider."""
    provider = SecondBackendProvider(_valid_payload())
    set_provider(provider)

    result = asyncio.run(run_monolithic_schema(TEST_WORDS[0], timeout=5))

    assert provider.calls == 1
    assert result["success"] is True
    # Contrato comun (AGENTS.md): dict plano con estas claves, no una tupla.
    for key in ("success", "text_output", "duration", "total_tokens", "cost", "timed_out"):
        assert key in result

    validation = validate_dictionary_output(result["text_output"], expected_levels=FULL_LEVELS)
    assert validation["ok"], validation["errors"]
