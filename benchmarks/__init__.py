"""Harness de benchmark reproducible en modo replay (sin red, sin API key).

- ``benchmarks/fixtures/``: fixtures versionadas derivadas de corridas reales.
- ``benchmarks.replay_provider``: ``InferenceProvider`` deterministico que
  reproduce latencias y respuestas grabadas.
- ``benchmarks.run``: CLI que corre las 8 estrategias N veces contra el replay,
  emite p50/p95/p99 + n + IC95 a ``benchmarks/results.json`` y (con ``--check``)
  falla si la latencia RELATIVA entre estrategias regresa mas alla del umbral.
- ``benchmarks.generate_fixture``: regenera la fixture desde los datasets
  reales versionados en ``benchmark_results/``.

Que verifica y que NO: el replay gatea que el codigo de orquestacion de cada
estrategia preserve el perfil de latencia RELATIVO grabado (una regresion de
codigo que serializa lo paralelo, agrega llamadas o rompe el contrato se
detecta). NO re-verifica los numeros absolutos contra la API viva: eso sigue
siendo trabajo de ``.github/workflows/live-eval.yml`` y de corridas manuales.
"""
