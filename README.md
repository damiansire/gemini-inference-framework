| Campo      | Descripción |
|------------|------------|
| Aviso | Este repositorio representa únicamente mis puntos de vista y enfoque personales y no ha sido revisado por pares; no lo tomes como una verdad absoluta hasta que se complete la revisión correspondiente. |
| Estado     | Pendiente de revisión por pares |


# Gemini Reasoning Explosion — Benchmark Empírico y Suite de Mitigación

> **TL;DR:** Un prompt para un diccionario de finlandés causa que `gemini-3-flash-preview` consuma **más de 62k tokens de pensamiento (thought tokens)** y tome **4 minutos y 19 segundos**. Construimos un benchmark de **120 llamadas API controladas** a través de **8 estrategias arquitectónicas** y descubrimos que la arquitectura de **Cascada Estructurada (Structured Cascade)** reduce esto a **17.2s con un 100% de fiabilidad** — sin cambiar el contenido del prompt.

---

## Contexto: El Problema

Este proyecto se originó a partir de una [discusión en GenAI Circle] que reportó latencia extrema y desperdicio de tokens con `gemini-3-flash-preview`:

| Métrica | Valor Reportado |
|---|---|
| Duración | **4 minutos 19 segundos** |
| Tokens de Entrada | ~3,400 |
| Tokens de Salida | ~1,069 |
| Tokens de Pensamiento | **62,910** |

El prompt genera entradas de diccionario estructuradas en JSON para palabras en finlandés, requiriendo ejemplos nivelados por CEFR y transformaciones fonológicas a finlandés hablado (`spokenFi`). Nuestra hipótesis de trabajo: el modelo entra en **bucles de razonamiento (reasoning loops)** debido a restricciones en competencia — estructura JSON estricta + generación creativa + reglas lingüísticas deterministas.

---

## Resultados del Benchmark (n=120)

**8 estrategias × 5 palabras × 3 iteraciones** — con invalidación de caché (cache busting) mediante UUID+epoch, orden de ejecución aleatorio, calentamiento del modelo (model warmup) y validación estructural de la salida.

| Estrategia | Latencia Promedio | Promedio Tokens Pensamiento | Máx Tokens Pensamiento | Costo Promedio (USD) | Tasa de Éxito | Tasa de Fallo |
|---|---|---|---|---|---|---|
| **Presupuesto de Pensamiento (LOW)** | **8.2s** ⚡ | **0** | 0 | $0.0007 | 93.3% | 6.7% |
| **Optimización Perezosa (Lazy) (A1-B1)** | **16.1s** | 2,586 | 6,620 | $0.0014 | 100% | 0% |
| **Cascada Estructurada (Cascade)** | **17.2s** ✅ | 3,862 | 10,195 | $0.0023 | **100%** | **0%** |
| Monolítica Optimizada | 20.7s | 2,645 | 5,785 | $0.0015 | 73.3% | 26.7% |
| Monolítica (Sin Schema) | 22.0s | 2,648 | 4,498 | $0.0018 | 100% | 0% |
| Monolítica (Schema Estricto) | 28.9s | 4,049 | 6,597 | $0.0024 | 100% | 0% |
| Modelo Pro (3.1) | 54.7s | 4,822 | 7,420 | **$0.0340** 💸 | 86.7% | 13.3% |
| **Pipeline (Multi-etapa)** | **152.9s** 🐌 | **10,713** | **18,144** | $0.0049 | 93.3% | 6.7% |

> **Palabras de prueba:** `hana`, `kuusi`, `juosta`, `vanha`, `silta` — elegidas deliberadamente por su variable ambigüedad léxica (hana = 3+ significados vs. silta = 1 significado claro).

---

## Hallazgos Clave

### 1. Causa Raíz: Fricción en las Instrucciones

Los 62k tokens de pensamiento emergen de tres modos cognitivos compitiendo en un solo prompt:

1. **Generación creativa** — oraciones en finlandés niveladas por CEFR y pedagógicamente apropiadas
2. **Transformación determinista** — 10 reglas fonológicas específicas para el `spokenFi`
3. **Estructura JSON estricta** — arreglos anidados, nombres de campos exactos, valores enum

El modelo deriva constantemente las reglas mientras se cuestiona si su salida creativa viola las restricciones estructurales, creando una espiral de razonamiento.

### 2. La Cascada Estructurada es la Solución para Producción

La **Cascada Estructurada** descompone la tarea en 3 etapas especializadas con controles de pensamiento por etapa:

| Etapa | Tarea | Nivel de Pensamiento | Temperatura |
|---|---|---|---|
| Etapa 1 | Extraer significados y definiciones | `LOW` | 0.2 |
| Etapa 2 | Generar ejemplos CEFR (en paralelo) | `LOW` | 0.7 |
| Etapa 3 | Transformación SpokenFi (en paralelo) | `MINIMAL` | 0.0 |

**Resultado:** Promedio de 17.2s con **100% de tasa de éxito** a lo largo de las 15 ejecuciones. Las etapas 2 y 3 se ejecutan en paralelo vía `asyncio.gather`.

### 3. Pipeline es un Anti-Patrón

El hallazgo más contraintuitivo: **Pipeline (multi-etapa secuencial) es la peor estrategia con 152.9s**. Sin controles de pensamiento, la Etapa 3 (spokenFi) entra en espirales de razonamiento de 45 segundos por cada significado, uno a la vez. Cascade evita esto limitando el pensamiento de la Etapa 3 a `MINIMAL` y ejecutando los significados en paralelo.

### 4. El Modelo Pro No Resuelve Problemas Arquitectónicos

`gemini-3.1-pro-preview` promedió **54.7s a $0.034/llamada** — 19x más caro que Flash con una **menor fiabilidad (86.7%)**. Para tareas de generación estructurada, la arquitectura supera el poder bruto del modelo.

### 5. Suprimir el Pensamiento es Rápido pero Frágil

`thinking_level=LOW` produce los resultados más rápidos (8.2s) con **cero tokens de pensamiento**, pero sacrifica el **6.7% de las salidas** a errores de validación JSON. Aceptable con lógica de reintentos; no apto para una producción tipo fire-and-forget.

---

## Estrategias Probadas

| # | Estrategia | Descripción | Insight Clave |
|---|----------|-------------|-------------|
| 1 | Monolítica (Sin Schema) | Prompt original — control de referencia | 22s prom, 100% fiable |
| 2 | Monolítica (Schema Estricto) | Cumplimiento vía `response_schema` a nivel de API | +31% de latencia vs referencia por la carga adicional de cumplir el schema |
| 3 | Monolítica Optimizada | Prompt más corto con patrones Few-Shot | Rápida pero con 26.7% de tasa de fallo |
| 4 | Optimización Perezosa (A1-B1) | Solo genera 3 niveles CEFR en vez de 6 | Mejor rendimiento/costo para salidas parciales |
| 5 | **Cascada Estructurada** | Pensamiento por etapa + ejecución en paralelo | **Ganadora en Producción — 17.2s, 100% de éxito** |
| 6 | Pipeline (Multi-etapa) | Descomposición secuencial, sin control de pensamiento | La peor: 152.9s, espirales de razonamiento en la Etapa 3 |
| 7 | Presupuesto de Pensamiento (LOW) | Monolítica con `thinking_level=LOW` | La más rápida con 8.2s, pero 6.7% de salidas malformadas |
| 8 | Modelo Pro | `gemini-3.1-pro-preview` | Costo 19x, menor fiabilidad que el modelo Flash con buena arquitectura |

---

## Estructura del Proyecto

```
├── compare_benchmarks.py    # Orquestador principal (120+ ejecuciones, generación de reportes)
├── prompts.py               # Todas las variantes de prompts, system messages, schemas
├── .env                     # GOOGLE_API_KEY
├── strategies/
│   ├── monolithic/          # Estrategia base (baseline)
│   ├── monolithic_schema/   # Cumplimiento estricto del schema
│   ├── optimized_monolithic/# Prompt few-shot acortado
│   ├── lazy_optimized/      # CEFR Parcial (solo A1-B1)
│   ├── cascade/             # ✅ Cascada Estructurada (producción)
│   ├── pipeline/            # Multi-etapa secuencial  
│   ├── thinking_budget/     # Límite con thinking_level=LOW
│   ├── pro_model/           # gemini-3.1-pro-preview
│   ├── output_validation.py # Validador estructural JSON + CEFR
│   └── utils.py             # Compartido: tasas de costo, métricas, helpers de API
├── benchmark_results/       # Reportes generados, JSONs raw, borradores
├── docs/
│   ├── ARCHITECTURE.md      # Análisis técnico de la explosión de razonamiento
│   └── ...
└── dashboard/               # UI de visualización
    ├── index.html
    ├── index.css
    └── app.js
```

---

## Inicio Rápido

```bash
# 1. Instalar dependencias
./venv/bin/pip install google-genai python-dotenv

# 2. Prueba rápida de humo (1 palabra, 1 iteración)
./venv/bin/python compare_benchmarks.py --words silta --iterations 1

# 3. Benchmark completo (las 8 estrategias, 5 palabras, 3 iteraciones = 120 llamadas)
./venv/bin/python compare_benchmarks.py \
  --strategies monolithic monolithic_schema optimized_monolithic lazy_optimized pipeline cascade thinking_budget pro_model \
  --iterations 3

# 4. Ver dashboard
./venv/bin/python -m http.server 8080
# Abrir http://localhost:8080/dashboard/
```

## Ejecuciones Personalizadas

```bash
# Probar estrategias específicas
./venv/bin/python compare_benchmarks.py --strategies monolithic cascade --iterations 5

# Probar palabras específicas
./venv/bin/python compare_benchmarks.py --words hana kuusi --iterations 3

# Ajustar el límite de tiempo (timeout, por defecto: 180s)
./venv/bin/python compare_benchmarks.py --timeout 240
```

---

## Recomendaciones para Producción

1. **Para entradas completas de diccionario (6 niveles CEFR + spokenFi):** Usar **Cascada Estructurada** — 17.2s, 100% de fiabilidad, $0.002/llamada.
2. **Para la máxima velocidad con tolerancia a reintentos:** Monolítica con `thinking_level=LOW` — 8.2s, requiere ~7% de tasa de reintento.
3. **Para contenido parcial (solo A1-B1):** Optimización Perezosa (Lazy Optimized) — 16.1s, 100% de fiabilidad, el costo más bajo.
4. **Evitar:** Pipeline sin controles de pensamiento. Modelo Pro para tareas de generación estructurada.

---

## Requisitos

- Python 3.10+
- SDK `google-genai`
- `python-dotenv`
- Clave de API de Google con acceso a Gemini (en `.env`)

---

*Metodología del Benchmark: invalidación de caché (cache busting) por llamada con UUID+epoch, orden de ejecución aleatorio, calentamiento del modelo, validación de la salida (estructura JSON + completitud del nivel CEFR). Modelos: `gemini-3-flash-preview`, `gemini-3.1-pro-preview`.*
