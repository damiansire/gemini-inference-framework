"""Tests de scripts/salvage.py: la reconstruccion desde logs no pierde clases.

El bug que fija esta suite: salvage degradaba un TIMEOUT a fallo generico
(sin ``timed_out``), asi que ``summarize_metrics`` reportaba 0 timeouts en
cualquier reporte regenerado desde un log, aunque el log los mostrara.
"""

from scripts.compare_benchmarks import summarize_metrics
from scripts.salvage import parse_run_records

_LOG = """
[1/6] Monolithic (No Schema) | word='hana' | iteration=1 | salt=abcd1234
  VALID | dur=21.5s | ttft=1.2s | thought=2,600 | total=5,100 | api_success=True | output_valid=True
[2/6] Monolithic (No Schema) | word='hana' | iteration=2 | salt=beef5678
  TIMEOUT | dur=180.00s | ttft=N/A | thought=0 | total=0 | api_success=False | output_valid=False
[3/6] Pro Model | word='hana' | iteration=1 | salt=cafe9012
  FAILED | dur=3.10s | ttft=N/A | thought=0 | total=120 | api_success=True | output_valid=False
"""


def test_parse_preserva_las_tres_clasificaciones():
    records = parse_run_records(_LOG)
    assert len(records) == 3

    valid, timeout, failed = records
    assert valid["success"] is True
    assert valid["timed_out"] is False

    # El corazon del fix: TIMEOUT no se degrada a error generico.
    assert timeout["success"] is False
    assert timeout["timed_out"] is True

    assert failed["success"] is False
    assert failed["timed_out"] is False
    assert failed["api_success"] is True
    assert failed["output_valid"] is False


def test_summarize_metrics_cuenta_los_timeouts_salvageados():
    records = [r for r in parse_run_records(_LOG) if r["strategy"] == "monolithic"]
    summary = summarize_metrics(records)
    assert summary["total_runs"] == 2
    assert summary["successful_runs"] == 1
    assert summary["timeout_runs"] == 1


def test_parse_mapea_nombre_display_a_strategy_key():
    records = parse_run_records(_LOG)
    assert records[0]["strategy"] == "monolithic"
    assert records[2]["strategy"] == "pro_model"


def test_parse_log_vacio_devuelve_lista_vacia():
    assert parse_run_records("sin bloques de benchmark aca") == []
