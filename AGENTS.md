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
| `strategies/<nombre>/runner.py` | Una estrategia de inferencia. Expone `run_<nombre>(word, salt=None, timeout=...)` y devuelve `(result, metrics)`. |
| `strategies/output_validation.py` | Motor de asserts: valida y normaliza la salida del modelo. Devuelve `{"ok", "errors", "normalized"}`. Codigo de correccion: tratar como codigo de seguridad. |
| `strategies/utils.py` | Cliente Gemini compartido, modelos, tarifas y `MetricsTracker`. |
| `prompts.py` | Prompts por estrategia/etapa. |
| `compare_benchmarks.py` | Registro `STRATEGIES` + orquestacion del benchmark y reporte. |
| `salvage.py` | Recuperacion de resultados desde logs. |
| `tests/` | Tests con pytest. `test_output_validation.py` cubre el validador adversarialmente. |
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

Toda strategy expone la misma firma y forma de resultado (hoy implicito; tratarlo
como contrato):

- `async def run_<nombre>(word, salt=None, timeout=...) -> (result, metrics)`.
- `result` debe pasar `validate_dictionary_output(...)` con los `expected_levels`
  declarados para esa strategy en `STRATEGIES`.
- `metrics` es un `MetricsTracker` (o equivalente) con tokens/duraciones.

## Definition of done: agregar una strategy nueva

1. `strategies/<nombre>/runner.py` con `run_<nombre>(word, salt=None, timeout=...)`
   que respeta el contrato comun.
2. `strategies/<nombre>/__init__.py`.
3. Prompts en `prompts.py`.
4. Registro en `STRATEGIES` (`compare_benchmarks.py`) con `runner` y
   `expected_levels`.
5. Test que valide que el `result` pasa `validate_dictionary_output` y, si la
   strategy parsea o transforma salida, su rama adversarial.

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
