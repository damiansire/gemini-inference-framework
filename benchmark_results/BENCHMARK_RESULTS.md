# Reporte del Benchmark de Latencia de Gemini

Generado: 2026-04-10 16:33:40
Palabras: hana, kuusi, juosta, vanha, silta
Iteraciones por estrategia: 3
Timeout por llamada: 180s
Modelos evaluados: gemini-3-flash-preview, gemini-3.1-pro-preview

## Resumen Ejecutivo

| Métrica | Monolítica (Sin Schema) | Monolítica (Schema Estricto) | Monolítica Optimizada | Optimización Perezosa (A1-B1) | Pipeline (Multi-etapa) | Cascada Estructurada | Presupuesto de Pensamiento (4096) | Modelo Pro |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Latencia Promedio (E2E)** | 21.98s | 28.88s | 20.70s | 16.14s | 152.89s | 17.23s | 8.21s | 54.67s |
| **Tiempo al Primer Token (TTFT)** | 15.70s | 0.00s | 14.46s | 13.37s | 0.00s | 0.00s | 2.12s | 42.17s |
| **Promedio Tokens de Pensamiento** | 2,648 | 4,049 | 2,645 | 2,586 | 10,713 | 3,862 | 0 | 4,822 |
| **Promedio Total de Tokens** | 7,704 | 8,950 | 4,609 | 3,913 | 13,983 | 8,704 | 4,876 | 10,338 |
| **Costo Promedio por Solicitud** | $0.00180 | $0.00235 | $0.00149 | $0.00141 | $0.00485 | $0.00227 | $0.00073 | $0.03400 |
| **Tasa de Éxito de API** | 100% | 100% | 80% | 100% | 93% | 100% | 100% | 93% |
| **Tasa de Salidas Válidas** | 100% | 100% | 73% | 100% | 93% | 100% | 93% | 87% |

## Control de Calidad

Todas las métricas de la tabla anterior se calculan únicamente a partir de las ejecuciones que completaron y pasaron el validador de salida.
El validador verifica que el JSON sea parseable, la forma del nodo raíz, las claves requeridas, la cobertura de niveles CEFR y una política de lema (headword) que rechaza colisiones obvias con formas gramaticales.

## Notas sobre las Estrategias

- Optimización Perezosa es la estrategia de salida parcial más rápida con un promedio de latencia de 16.14s.
- La estrategia completamente válida más rápida es Optimización Perezosa (A1-B1) con un promedio de latencia de 16.14s.
- Fuera de la variante perezosa, el enfoque de menor latencia es Presupuesto de Pensamiento (4096).
- El cumplimiento del schema cambió el uso promedio de tokens de pensamiento en +52.9% versus la línea base monolítica.

## Desglose de Fallos

- Monolítica (Sin Schema): 15/15 ejecuciones válidas, 0 fallos de validación, 0 fallos de API.
- Monolítica (Schema Estricto): 15/15 ejecuciones válidas, 0 fallos de validación, 0 fallos de API.
- Monolítica Optimizada: 11/15 ejecuciones válidas, 1 fallo de validación, 3 fallos de API.
- Optimización Perezosa (A1-B1): 15/15 ejecuciones válidas, 0 fallos de validación, 0 fallos de API.
- Pipeline (Multi-etapa): 14/15 ejecuciones válidas, 0 fallos de validación, 1 fallo de API.
- Cascada Estructurada: 15/15 ejecuciones válidas, 0 fallos de validación, 0 fallos de API.
- Presupuesto de Pensamiento (4096): 14/15 ejecuciones válidas, 1 fallo de validación, 0 fallos de API.
- Modelo Pro: 13/15 ejecuciones válidas, 1 fallo de validación, 1 fallo de API.
