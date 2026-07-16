"""Provider de replay deterministico (implementa ``InferenceProvider``).

Reproduce, sin red ni API key, el perfil de latencia de corridas reales: cada
"llamada" duerme la duracion grabada en la fixture (escalada por
``time_scale``) y devuelve la respuesta canned correspondiente. Determinismo:
la iteracion i de una estrategia usa siempre ``durations_s[i % n]``, asi que
dos corridas con los mismos parametros producen los mismos percentiles (modulo
el jitter del event loop, cubierto por el umbral del gate en ``benchmarks.run``).

El harness declara la estrategia activa con ``begin_run``; dentro de una
estrategia multi-etapa, el stage se despacha por la forma del
``response_schema`` (mismo criterio que ``tests/test_concurrency.py``).
"""

import asyncio
import json
from pathlib import Path

DEFAULT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "replay_v1.json"


def load_fixture(path=DEFAULT_FIXTURE):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class _ReplayUsage:
    def __init__(self, usage_dict):
        self.prompt_token_count = usage_dict["prompt_token_count"]
        self.candidates_token_count = usage_dict["candidates_token_count"]
        self.thoughts_token_count = usage_dict["thoughts_token_count"]
        self.total_token_count = usage_dict["total_token_count"]


class _ReplayResponse:
    def __init__(self, *, parsed=None, text="", usage=None):
        self.parsed = parsed
        self.text = text
        self.usage_metadata = usage


class _ReplayChunk:
    def __init__(self, text, usage):
        self.text = text
        self.usage_metadata = usage


class ReplayProvider:
    """``InferenceProvider`` que reproduce latencias/respuestas grabadas."""

    def __init__(self, fixture=None, time_scale=None):
        self.fixture = fixture if fixture is not None else load_fixture()
        scale = self.fixture["time_scale"] if time_scale is None else time_scale
        self.time_scale = scale
        self.models_seen = []
        self.total_calls = 0
        self._strategy_key = None
        self._spec = None
        self._run_duration = None

    def begin_run(self, strategy_key, iteration):
        """Fija la estrategia activa y la duracion grabada de esta iteracion."""
        spec = self.fixture["strategies"][strategy_key]
        durations = spec["durations_s"]
        self._strategy_key = strategy_key
        self._spec = spec
        self._run_duration = durations[iteration % len(durations)]

    # -- despacho interno ----------------------------------------------------

    def _require_run(self):
        if self._spec is None:
            raise RuntimeError("ReplayProvider: llama begin_run() antes de usar el provider")
        return self._spec

    def _entry_payload(self):
        key = "lazy_entry" if self._spec["levels"] == "lazy" else "full_entry"
        return self.fixture["payloads"][key]

    def _stage_for(self, config):
        schema = getattr(config, "response_schema", None)
        props = getattr(schema, "properties", {}) or {}
        if "meanings" in props:
            return "stage1"
        if "examples" in props:
            return "stage2"
        if "spoken_examples" in props:
            return "stage3"
        raise RuntimeError(
            f"ReplayProvider: schema de stage no reconocido para '{self._strategy_key}'"
        )

    def _stage_latency(self, stage):
        duration = self._run_duration
        split = self._spec["stage_split"]
        if self._spec["kind"] == "multistage_parallel":
            # cascade: e2e = s1 + (s2 + s3), las M ramas corren en paralelo.
            return duration * split[stage]
        # pipeline: e2e = s1 + M * (s2 + s3), las ramas corren en secuencia.
        num_meanings = self.fixture["num_meanings"]
        rest = duration * (1 - split["stage1"])
        per_meaning = rest / num_meanings
        if stage == "stage1":
            return duration * split["stage1"]
        if stage == "stage2":
            return per_meaning * split["stage2_fraction_of_rest"]
        return per_meaning * (1 - split["stage2_fraction_of_rest"])

    async def _sleep(self, latency_s):
        scaled = latency_s * self.time_scale
        if scaled > 0:
            await asyncio.sleep(scaled)

    def _usage(self):
        return _ReplayUsage(self._spec["usage"])

    # -- contrato InferenceProvider -------------------------------------------

    async def generate_content(self, *, model, contents, config):
        spec = self._require_run()
        self.models_seen.append(model)
        self.total_calls += 1
        if spec["kind"].startswith("multistage"):
            stage = self._stage_for(config)
            await self._sleep(self._stage_latency(stage))
            return _ReplayResponse(parsed=self.fixture["payloads"][stage], usage=self._usage())
        # single_sync (monolithic_schema): el SDK entrega .parsed por el schema.
        await self._sleep(self._run_duration)
        return _ReplayResponse(parsed=self._entry_payload(), usage=self._usage())

    async def generate_content_stream(self, *, model, contents, config):
        spec = self._require_run()
        self.models_seen.append(model)
        self.total_calls += 1
        if spec["kind"].startswith("multistage"):
            raise RuntimeError(
                "ReplayProvider: las estrategias multi-etapa usan el camino non-streaming"
            )
        text = json.dumps(self._entry_payload(), ensure_ascii=False)
        usage = self._usage()
        latency_s = self._run_duration

        async def _stream():
            await self._sleep(latency_s)
            yield _ReplayChunk(text, usage)

        return _stream()
