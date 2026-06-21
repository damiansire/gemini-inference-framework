"""Tests de regresion de la capa de concurrencia/resiliencia (Fase 2).

SIN API key ni red: se inyecta un provider MOCK que cuenta el pico de requests
in-flight. La medicion (`medicion_fase2.md`) habia confirmado que el fan-out de
`cascade` escala a W·M sin tope (100 con 20 palabras × 5 acepciones). Estos
tests afirman la propiedad inversa: con el ``asyncio.Semaphore`` compartido en
``utils`` (limite=K), el in-flight pico NUNCA supera K, ni siquiera bajo un
caller concurrente W·M >> K.

Tambien se cubre el retry con backoff (transitorio vs fatal y Retry-After).

Se sigue el patron de la suite (``asyncio.run``, sin pytest-asyncio).
"""

import asyncio

import pytest
from google.genai import errors as genai_errors

from strategies import utils
from strategies.cascade import runner as cascade_runner


class _InflightProvider:
    """Provider mock que cuenta el pico de llamadas concurrentes.

    Despacha por la forma del ``response_schema`` (stage1/2/3) para devolver un
    objeto-respuesta con ``.parsed`` correcto, de modo que ``run_cascade``
    avance sin tocar la red.
    """

    def __init__(self, num_meanings, net_latency_s=0.01):
        self.num_meanings = num_meanings
        self.net_latency_s = net_latency_s
        self.current = 0
        self.max_inflight = 0
        self.total_calls = 0
        self._lock = asyncio.Lock()

    async def _enter(self):
        async with self._lock:
            self.current += 1
            self.total_calls += 1
            if self.current > self.max_inflight:
                self.max_inflight = self.current

    async def _leave(self):
        async with self._lock:
            self.current -= 1

    def _payload_for(self, config):
        schema = getattr(config, "response_schema", None)
        props = getattr(schema, "properties", {}) or {}
        if "meanings" in props:
            parsed = {
                "meanings": [
                    {
                        "englishDefinition": f"meaning #{i}",
                        "definiendum": f"def{i}",
                        "synonyms": [],
                        "antonyms": [],
                    }
                    for i in range(self.num_meanings)
                ]
            }
        elif "examples" in props:
            parsed = {
                "examples": [
                    {"sourceFi": f"lause {lvl}", "level": lvl}
                    for lvl in ["a1", "a2", "b1", "b2", "c1", "c2"]
                ]
            }
        elif "spoken_examples" in props:
            parsed = {
                "spoken_examples": [
                    {"spokenFi": f"puhe {lvl}", "level": lvl}
                    for lvl in ["a1", "a2", "b1", "b2", "c1", "c2"]
                ]
            }
        else:
            parsed = {}
        return _FakeResponse(parsed)

    async def generate_content(self, *, model, contents, config):
        await self._enter()
        try:
            await asyncio.sleep(self.net_latency_s)
            return self._payload_for(config)
        finally:
            await self._leave()

    async def generate_content_stream(self, *, model, contents, config):  # pragma: no cover
        raise NotImplementedError


class _FakeResponse:
    def __init__(self, parsed):
        self.parsed = parsed
        self.text = ""
        self.usage_metadata = None


@pytest.fixture(autouse=True)
def _restore_provider_and_semaphore():
    """Restaura provider y Semaphore reales tras cada test."""
    original = utils.get_provider()
    yield
    utils.set_provider(original)
    utils.reset_inference_semaphore()


def _run_caller_concurrent(words, meanings, limit, monkeypatch):
    """Corre W palabras en paralelo (W·M fan-out) y devuelve el pico in-flight."""
    monkeypatch.setenv("GEMINI_MAX_CONCURRENCY", str(limit))
    provider = _InflightProvider(num_meanings=meanings)
    utils.set_provider(provider)
    utils.reset_inference_semaphore()

    async def caller():
        # W palabras en paralelo: el escenario que el benchmark secuencial
        # enmascara y que `medicion_fase2.md` midio en W·M sin tope.
        await asyncio.gather(
            *(cascade_runner.run_cascade(word=f"w{i}", timeout=120.0) for i in range(words))
        )

    # Silenciar los print() de progreso del runner.
    import builtins

    real_print = builtins.print
    builtins.print = lambda *a, **k: None
    try:
        asyncio.run(caller())
    finally:
        builtins.print = real_print
    return provider.max_inflight, provider.total_calls


def test_inflight_capeado_por_semaphore_caller_concurrente(monkeypatch):
    """W·M = 20×5 = 100 sin tope; con Semaphore(K=5) el pico debe ser <= 5."""
    limit = 5
    max_inflight, total_calls = _run_caller_concurrent(
        words=20, meanings=5, limit=limit, monkeypatch=monkeypatch
    )
    # Sin tope esto seria 100 (W·M). Con el Semaphore nunca supera K.
    assert max_inflight <= limit, f"in-flight {max_inflight} supero el limite {limit}"
    # Sanity: se hicieron las llamadas esperadas (1 + 2*M por palabra).
    assert total_calls == 20 * (1 + 2 * 5)


def test_inflight_satura_hasta_el_limite(monkeypatch):
    """Con carga >> K, el pico debe LLEGAR a K (el tope se usa, no infra-utiliza)."""
    limit = 3
    max_inflight, _ = _run_caller_concurrent(
        words=10, meanings=5, limit=limit, monkeypatch=monkeypatch
    )
    assert max_inflight == limit, f"esperaba saturar a {limit}, pico={max_inflight}"


def test_limite_distinto_se_respeta(monkeypatch):
    limit = 8
    max_inflight, _ = _run_caller_concurrent(
        words=20, meanings=5, limit=limit, monkeypatch=monkeypatch
    )
    assert max_inflight <= limit


# --- Retry / backoff ---------------------------------------------------------


def _api_error(code):
    return genai_errors.APIError(code, {"error": {"message": "boom"}})


def test_retry_reintenta_transitorio_y_converge():
    """Falla 2 veces con 429 y luego responde: with_retries debe converger."""
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _api_error(429)
        return "ok"

    async def fake_sleep(_):
        return None

    result = asyncio.run(utils.with_retries(factory, sleep=fake_sleep))
    assert result == "ok"
    assert calls["n"] == 3


def test_retry_no_reintenta_fatal():
    """Un 400 (config/request) es fatal: no se reintenta, propaga al toque."""
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        raise _api_error(400)

    async def fake_sleep(_):  # pragma: no cover - no deberia llamarse
        raise AssertionError("no debe dormir ante un fatal")

    with pytest.raises(genai_errors.APIError):
        asyncio.run(utils.with_retries(factory, sleep=fake_sleep))
    assert calls["n"] == 1


def test_retry_agota_intentos():
    """Transitorio persistente: agota max_attempts y propaga el ultimo error."""
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        raise _api_error(503)

    async def fake_sleep(_):
        return None

    with pytest.raises(genai_errors.APIError):
        asyncio.run(utils.with_retries(factory, max_attempts=3, sleep=fake_sleep))
    assert calls["n"] == 3


def test_retry_respeta_retry_after():
    """Si el 429 trae Retry-After, with_retries duerme ese tiempo exacto."""
    slept = []

    class _Resp:
        headers = {"Retry-After": "7"}

    err = _api_error(429)
    err.response = _Resp()

    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        if calls["n"] == 1:
            raise err
        return "ok"

    async def fake_sleep(seconds):
        slept.append(seconds)

    result = asyncio.run(utils.with_retries(factory, sleep=fake_sleep))
    assert result == "ok"
    assert slept == [7.0]
