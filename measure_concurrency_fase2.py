"""Medicion Fase 2 (GATED) — concurrencia estructural del fan-out de cascade.

NO optimiza nada. Caracteriza, con un cliente Gemini MOCKEADO (sin API key, sin
red), cuantas requests concurrentes (in-flight) dispara `run_cascade` por palabra
y las compara con `run_pipeline`. Confirma o refuta la hipotesis de "unbounded
gather" (strategies/cascade/runner.py:~211).

Como funciona:
- Monkeypatch de `generate_content_sync` en utils + en los dos runners (ya lo
  importaron por nombre) por un stub async que:
    * incrementa un contador global de in-flight, registra el maximo observado,
    * duerme un poquito (simula latencia de red) para que las corrutinas
      concurrentes coexistan de verdad en el tiempo,
    * decrementa al salir,
    * devuelve el payload estructurado correcto segun la etapa (stage1/2/3),
      poniendo `parsed` para no depender de parse_payload.
- Se corre cascade con N meanings = 1,2,3,5,8,12 y pipeline para contraste.

Lo MEDIDO aca: grado de concurrencia estructural (in-flight maximo, total de
llamadas). Lo NO medido: 429s reales / latencias / cuotas (requieren API key y
trafico real).
"""

import asyncio

from strategies import utils
from strategies.cascade import runner as cascade_runner
from strategies.pipeline import runner as pipeline_runner


class InflightTracker:
    def __init__(self):
        self.current = 0
        self.max_inflight = 0
        self.total_calls = 0
        self._lock = asyncio.Lock()

    async def enter(self):
        async with self._lock:
            self.current += 1
            self.total_calls += 1
            if self.current > self.max_inflight:
                self.max_inflight = self.current

    async def leave(self):
        async with self._lock:
            self.current -= 1


def _make_stage1(num_meanings):
    return {
        "meanings": [
            {
                "englishDefinition": f"meaning #{i}",
                "definiendum": f"def{i}",
                "synonyms": [],
                "antonyms": [],
            }
            for i in range(num_meanings)
        ]
    }


_STAGE2 = {
    "examples": [
        {"sourceFi": f"lause {lvl}", "level": lvl} for lvl in ["a1", "a2", "b1", "b2", "c1", "c2"]
    ]
}

_STAGE3 = {
    "spoken_examples": [
        {"spokenFi": f"puhe {lvl}", "level": lvl} for lvl in ["a1", "a2", "b1", "b2", "c1", "c2"]
    ]
}


def make_mock(tracker, num_meanings, net_latency_s=0.02):
    """Devuelve un stub async compatible con generate_content_sync.

    Despacha por la forma del response_schema (stage1/2/3) que vive en
    config.response_schema. Cuenta in-flight con un pequenio sleep para que la
    concurrencia se manifieste en el tiempo.
    """

    async def _mock_generate_content_sync(model, contents, config, timeout=None):
        await tracker.enter()
        try:
            await asyncio.sleep(net_latency_s)

            schema = getattr(config, "response_schema", None)
            props = getattr(schema, "properties", {}) or {}
            if "meanings" in props:
                parsed = _make_stage1(num_meanings)
            elif "examples" in props:
                parsed = _STAGE2
            elif "spoken_examples" in props:
                parsed = _STAGE3
            else:
                parsed = {}

            return {
                "text": "",
                "parsed": parsed,
                "usage": None,  # _extract_usage tolera None -> 0,0,0,0
                "duration": net_latency_s,
                "ttft": None,
            }
        finally:
            await tracker.leave()

    return _mock_generate_content_sync


def patch_all(mock):
    """Parchea generate_content_sync donde lo consumen.

    Los runners hacen `from ..utils import generate_content_sync`, asi que el
    nombre quedo ligado en el modulo del runner: hay que parchear ahi tambien.
    """
    utils.generate_content_sync = mock
    cascade_runner.generate_content_sync = mock
    pipeline_runner.generate_content_sync = mock


async def measure_cascade(num_meanings):
    tracker = InflightTracker()
    mock = make_mock(tracker, num_meanings)
    patch_all(mock)
    await cascade_runner.run_cascade(word="x", timeout=120.0)
    return tracker.max_inflight, tracker.total_calls


async def measure_pipeline(num_meanings):
    tracker = InflightTracker()
    mock = make_mock(tracker, num_meanings)
    patch_all(mock)
    await pipeline_runner.run_pipeline(word="x", timeout=120.0)
    return tracker.max_inflight, tracker.total_calls


async def main():
    import builtins

    # Silenciar los print() de progreso de los runners para limpiar la salida.
    real_print = builtins.print

    def quiet(*a, **k):
        pass

    meanings_grid = [1, 2, 3, 5, 8, 12]

    rows = []
    for n in meanings_grid:
        builtins.print = quiet
        c_max, c_total = await measure_cascade(n)
        p_max, p_total = await measure_pipeline(n)
        builtins.print = real_print
        rows.append((n, c_max, c_total, p_max, p_total))

    print("=" * 78)
    print("  MEDICION FASE 2 — concurrencia estructural (cliente Gemini MOCKEADO)")
    print("  in-flight = requests concurrentes simultaneas observadas (pico)")
    print("=" * 78)
    header = (
        f"{'meanings':>9} | {'cascade in-flight':>17} | {'cascade calls':>13} | "
        f"{'pipeline in-flight':>18} | {'pipeline calls':>14}"
    )
    print(header)
    print("-" * len(header))
    for n, c_max, c_total, p_max, p_total in rows:
        print(f"{n:>9} | {c_max:>17} | {c_total:>13} | {p_max:>18} | {p_total:>14}")
    print("-" * len(header))
    print(
        "Lectura: en cascade el in-flight pico == nº de meanings (sin tope: escala "
        "lineal).\n"
        "         total calls cascade == 1 (stage1) + 2*meanings (stage2+stage3).\n"
        "         pipeline mantiene in-flight == 1 (estrictamente secuencial)."
    )


if __name__ == "__main__":
    asyncio.run(main())
