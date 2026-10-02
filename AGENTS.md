# AGENTS.md

Guia para agentes (Claude Code, Codex, etc.) trabajando en
`gemini-inference-framework`. Fuente unica de verdad: `CLAUDE.md` solo importa
este archivo (`@AGENTS.md`).

## Que es

Framework para comparar estrategias de inferencia multi-etapa sobre Gemini
(generacion de entradas de diccionario Finlandes -> Ingles). Cada estrategia es
un runner asincrono; el comparador las corre todas y produce metricas de costo,
tokens y latencia. El validador de salida decide si una respuesta del modelo es
aceptable.

## Estructura

| Ruta | Responsabilidad |
| --- | --- |
| `strategies/<nombre>/runner.py` | Una estrategia de inferencia. Expone `run_<nombre>(word, salt=None, timeout=...)`; la version registrada devuelve un dict plano (ver "Contrato comun"). |
| `strategies/output_validation.py` | Motor de asserts: valida y normaliza la salida del modelo. Devuelve `{"ok", "errors", "normalized"}`. Codigo de correccion: tratar como codigo de seguridad. |
| `strategies/utils.py` | Cliente Gemini compartido, modelos, tarifas y `MetricsTracker`. |
| `prompts.py` | Prompts por estrategia/etapa. |
| `scripts/compare_benchmarks.py` | Registro `STRATEGIES` + orquestacion del benchmark y reporte. Se corre `python -m scripts.compare_benchmarks`. |
| `scripts/salvage.py` | Recuperacion de resultados desde logs. |
| `scripts/measure_concurrency_*.py`, `scripts/merge_extended_corpus.py` | Mediciones puntuales y merge one-off de datasets. |
| `benchmarks/` | Harness de replay deterministico (fixtures versionadas, `ReplayProvider`, `python -m benchmarks.run --check` = gate nightly de latencia relativa via `bench.yml`). |
| `tests/` | Tests con pytest. `test_output_validation.py` cubre el validador adversarialmente; `test_strategy_<nombre>.py` (uno por estrategia registrada, 8/8) cubre contrato + validez de salida contra el `ReplayProvider`. |
| `dashboard/` | UI estatica para visualizar resultados. |

Leer el AGENTS.md local relevante cuando exista al trabajar dentro de un
directorio.

## Comandos

| Tarea | Comando |
| --- | --- |
| Tests | `python -m pytest` |
| Lint | `python -m ruff check .` |
| Format | `python -m ruff format .` |

## Contrato comun de una strategy

Toda strategy **registrada en `STRATEGIES`** expone la misma firma y devuelve un
**dict plano** (no una tupla). Es lo que el orquestador consume: `_normalize_result`
hace `result.get(...)` sobre ese dict (`scripts/compare_benchmarks.py`).

- `async def run_<nombre>(word, salt=None, timeout=...) -> dict`.
- El `dict` lleva al menos: `success` (bool), `text_output` (la salida del modelo
  que se valida), `duration`, `ttft`, `prompt_tokens`, `candidate_tokens`,
  `thought_tokens`, `total_tokens`, `cost`, `timed_out`; en error, `error` (str)
  con `success=False`.
- La FORMA del dict vive en codigo, no solo en esta prosa: los helpers
  `inference_success_result` / `success_result_from_payload` /
  `inference_failure_result` (`strategies/utils.py`) son el UNICO lugar donde
  se arma. Agregar un campo al contrato = tocar esos helpers + este archivo;
  `tests/test_result_contract.py` fija la forma y la simetria exito/fallo.
  No armar el dict a mano en un runner nuevo.
- `text_output` debe pasar `validate_dictionary_output(...)` con los
  `expected_levels` declarados para esa strategy en `STRATEGIES`.

> Nota: las **bases** `run_cascade`/`run_pipeline` (`strategies/cascade`,
> `strategies/pipeline`) devuelven `(result, metrics)` con un `MetricsTracker`,
> pero **no se registran directamente**: `scripts/compare_benchmarks.py` las envuelve en
> el dict plano de arriba (`run_cascade_strategy`/`run_pipeline_strategy`). Lo que
> se registra siempre es la version envuelta que devuelve dict.

## Definition of done: agregar una strategy nueva

1. `strategies/<nombre>/runner.py` con `run_<nombre>(word, salt=None, timeout=...)`
   que respeta el contrato comun.
2. `strategies/<nombre>/__init__.py`.
3. Prompts en `prompts.py`.
4. Registro en `STRATEGIES` (`scripts/compare_benchmarks.py`) con `runner` y
   `expected_levels`.
5. `tests/test_strategy_<nombre>.py` propio (la convencion es 1 archivo por
   estrategia registrada) que valide que el `text_output` del dict pasa
   `validate_dictionary_output` y, si la strategy parsea o transforma salida,
   su rama adversarial.
6. Entrada en la fixture de replay (`python -m benchmarks.generate_fixture`
   la regenera desde los datasets; sin corridas reales de la estrategia nueva
   no hay fixture, y el harness `benchmarks/run.py` falla explicito).

## Reglas duras

- Nunca usar `JSON.parse`/`json.loads` directo sobre la salida del modelo:
  pasar por `parse_payload`/`validate_dictionary_output`, que validan y dan un
  `error` accionable. Un assert que pasa por accidente es un falso negativo
  silencioso (el peor bug en un evaluador).
- Los errores del validador son parte de la API: si cambias el texto de un
  `error`, actualiza el test que lo afirma.
- Tests adversariales: cubrir cada rama de error, no solo el happy path, y
  comparar el dict de salida completo (no solo `ok`).
- Nunca hashear ni loguear secretos (API keys de Gemini). El lint incluye
  flake8-bandit (`S`) por esto.

## Do Not

- No subir timeouts para "arreglar" un test lento: arregla el test.
- No commitear `.only`/`.skip` ni asserts deshabilitados.
- No commitear a `main` sin permiso, no `--force` sin permiso.
- Conventional commits en espanol. Sin atribucion a Claude ni `Co-Authored-By`.

## Barra de calidad

Todo codigo nuevo se escribe contra esta barra:

- **Nombres por dominio, no por mecanismo**: `run_<strategy>`,
  `validate_dictionary_output`, no `handle`/`process`/`data`.
- **Comentarios explican el PORQUE, nunca el QUE**: los comentarios existentes
  en `ci.yml`/`pyproject.toml` son el ejemplo (explican una decision no obvia,
  no parafrasean el codigo de al lado).
- **Contrato comun explicito y auto-documentado**: toda strategy registrada
  devuelve el mismo dict plano; no romper esa forma sin actualizar este archivo.
- **Fail-fast con limites explicitos**: toda llamada a Gemini pasa por un
  timeout; ningun retry/polling sin tope.
- **Validacion adversarial, no solo happy path** (ya cubierto arriba en
  "Reglas duras" y "Definition of done"): el estado queda consistente o el
  error es explicito, nunca a medias.
- **README con prueba real, no solo claim**, estado 2026-07-17:
  el claim ya no se afirma como verificado. El encabezado de la seccion avisa
  explicito ("single manual run (n=15 per strategy), not re-verified by CI,
  high variance") y ningun "100% reliability" encabeza el repo (las celdas de
  la tabla muestran el dato con su n e IC95 al lado, no como badge). La tabla
  del README NO se tipea a mano: se genera con `scripts/render_readme_table.py`
  desde un dataset versionado (`benchmark_results/readme_leaderboard_run.json`)
  entre los markers `<!-- BENCHMARK_TABLE:START/END -->`, con columnas de `n
  (valid/total)` e `95% CI (latency)` por estrategia. Lo que queda gateado
  ejecutablemente es: (a) la logica de seleccion del ganador
  (`tests/test_compare_benchmarks.py`), (b) contrato + validez de salida por
  estrategia (`tests/test_strategy_*.py`, 8/8), (c) el perfil de latencia
  RELATIVO del codigo de orquestacion via el harness de replay
  (`benchmarks/` + `bench.yml` nightly, falla si el p50 relativo se corre
  mas de +/-25% del esperado versionado), y (d) que la tabla del README este en
  sync con su dataset fuente (`tests/test_render_readme_table.py`; regenerar con
  `python -m scripts.render_readme_table --write`). Lo que sigue SIN gate
  automatico: los numeros absolutos contra la API viva. Para cerrarlo cuando el
  costo de API lo permita esta `regen-readme-table.yml` (manual/mensual, gateado
  en el secret `GOOGLE_API_KEY`): re-mide con n mas grande, recomputa IC95 y abre
  un PR con la tabla regenerada. live-eval.yml sigue muestreando semanal sin
  gatear. NO volver a subir el claim a "verificado" hasta que esa re-medicion
  live corra de verdad.

Las convenciones especificas de Python (config de ruff, patrones de pytest,
empaquetado) viven en `pyproject.toml` y `ci.yml`; esos archivos mandan.
