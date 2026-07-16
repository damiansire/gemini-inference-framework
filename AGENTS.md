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

## Estandar nivel mundial

Todo codigo nuevo se escribe contra esta barra (piso `fellow-standard.md` del
corpus de `/fragua`, `~/.claude/tools/_audit-tools/refs/architecture/`):

- **Nombres por dominio, no por mecanismo** (item a): `run_<strategy>`,
  `validate_dictionary_output`, no `handle`/`process`/`data`.
- **Comentarios explican el PORQUE, nunca el QUE** (item b) — ver los comentarios
  existentes en `ci.yml`/`pyproject.toml` como ejemplo (explican una decision no
  obvia, no parafrasean el codigo de al lado).
- **Contrato comun explicito y auto-documentado** (item c): toda strategy
  registrada devuelve el mismo dict plano; no romper esa forma sin actualizar
  este archivo.
- **Fail-fast con limites explicitos** (item i): toda llamada a Gemini pasa por
  un timeout; ningun retry/polling sin tope.
- **Validacion adversarial, no solo happy path** (ya cubierto arriba en
  "Reglas duras" y "Definition of done" — es el mismo principio que el item g
  del corpus: el estado queda consistente o el error es explicito, nunca a medias).
- **README con prueba real, no solo claim** (item l), estado 2026-07-16:
  el claim ya no se afirma como verificado. El README etiqueta la metrica
  22.0s->17.2s como "resultado historico de una corrida manual n=120,
  pendiente de verificacion CI-gated contra la API viva", y lo que SI queda
  gateado ejecutablemente es: (a) la logica de seleccion del ganador
  (`tests/test_compare_benchmarks.py`), (b) contrato + validez de salida por
  estrategia (`tests/test_strategy_*.py`, 8/8), y (c) el perfil de latencia
  RELATIVO del codigo de orquestacion via el harness de replay
  (`benchmarks/` + `bench.yml` nightly, falla si el p50 relativo se corre
  mas de +/-25% del esperado versionado). Lo que sigue SIN gate: los numeros
  absolutos contra la API viva (live-eval.yml los muestrea semanal pero no
  gatea). NO volver a subir el claim a "verificado" hasta que exista esa
  verificacion live gateada.

Gap de corpus conocido: `/fragua` todavia no tiene una nota `refs/python/`
(el enum de stacks cubre angular/react/rust/tauri/discord/creative/genai/
node-apis/text-rendering/ts-lib/node-ts, pero no python). Las reglas de arriba
salen del piso transversal (`fellow-standard.md`, no depende de stack); las
reglas python-especificas (ruff config, pytest patterns, packaging) siguen
siendo criterio ad-hoc hasta que alguien corra `/fragua evolucionar python`.
