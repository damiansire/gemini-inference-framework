"""Soporte comun de los tests por estrategia (uno por archivo, 8/8).

Cada estrategia registrada en ``STRATEGIES`` tiene su ``tests/test_strategy_
<nombre>.py`` que afirma, contra el ``ReplayProvider`` (fixtures versionadas de
``benchmarks/``): (1) el contrato comun de dict plano de AGENTS.md, (2) que el
``text_output`` pasa ``validate_dictionary_output`` con los ``expected_levels``
declarados, y (3) al menos una rama adversarial (error esperado de inferencia).
"""

from strategies.output_validation import validate_dictionary_output

# Contrato comun (AGENTS.md): toda strategy registrada devuelve un dict plano
# con al menos estas claves.
CONTRACT_KEYS = (
    "success",
    "text_output",
    "duration",
    "ttft",
    "prompt_tokens",
    "candidate_tokens",
    "thought_tokens",
    "total_tokens",
    "cost",
    "timed_out",
)


class FailingProvider:
    """Provider que siempre lanza ``exc``: ejercita la rama de error esperado."""

    def __init__(self, exc):
        self._exc = exc

    async def generate_content(self, *, model, contents, config):
        raise self._exc

    async def generate_content_stream(self, *, model, contents, config):
        raise self._exc


def assert_success_contract(result, expected_levels):
    """Contrato comun + quality gate sobre un resultado exitoso."""
    if result.get("success") is not True:
        raise AssertionError(f"run no exitoso: {result.get('error')}")
    missing = [key for key in CONTRACT_KEYS if key not in result]
    if missing:
        raise AssertionError(f"claves del contrato comun ausentes: {missing}")
    validation = validate_dictionary_output(result["text_output"], expected_levels=expected_levels)
    if not validation["ok"]:
        raise AssertionError(f"output invalido: {validation['errors']}")
