"""Gate: the README benchmark leaderboard is a machine-generated artifact.

The headline latency table used to be hand-typed prose, which is exactly the
kind of self-reported number that drifts from its data. These tests make the
table a *claim backed by an executable gate*: it must equal a fresh render of
its versioned source dataset, it must carry an explicit per-strategy ``n`` and
a 95% confidence interval, and the render must be deterministic. If someone
edits the table by hand (or the source data changes without re-rendering),
``test_readme_table_in_sync`` fails and points at the fix command.
"""

import json
from pathlib import Path

import pytest

from scripts.render_readme_table import (
    MARKER_END,
    MARKER_START,
    render_table,
    replace_table,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = REPO_ROOT / "benchmark_results" / "readme_leaderboard_run.json"
README_PATH = REPO_ROOT / "README.md"


@pytest.fixture
def data():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _readme_table_block():
    text = README_PATH.read_text(encoding="utf-8")
    assert MARKER_START in text and MARKER_END in text, "README lost the benchmark-table markers"
    inner = text.split(MARKER_START, 1)[1].split(MARKER_END, 1)[0]
    return inner.strip("\n")


def test_readme_table_in_sync(data):
    rendered = render_table(data).strip("\n")
    assert _readme_table_block() == rendered, (
        "README benchmark table is out of sync with its source data. "
        "Regenerate it: python -m scripts.render_readme_table --write"
    )


def test_render_is_deterministic(data):
    assert render_table(data) == render_table(data)


def test_render_includes_n_and_confidence_interval(data):
    rendered = render_table(data)
    # The columns that make the claim honest must be present.
    assert "n (valid/total)" in rendered
    assert "95% CI (latency)" in rendered
    # A CI is a real bracketed interval, not a bare point estimate.
    assert "[15.0s, 19.4s]" in rendered  # Structured Cascade, from the recorded run
    assert "15/15" in rendered  # a full-n strategy


def test_render_orders_by_latency_valid_first(data):
    rendered = render_table(data)
    body = [line for line in rendered.splitlines() if line.startswith("| ") and "---" not in line]
    # Skip the header row; the fastest valid strategy leads, the slowest trails.
    assert "Thinking Budget (LOW)" in body[1]
    assert "Pipeline (Multi-stage)" in body[-1]


def test_replace_table_requires_markers():
    with pytest.raises(ValueError, match="markers"):
        replace_table("no markers here", "table")


def test_replace_table_roundtrip(data):
    original = f"before\n{MARKER_START}\nOLD\n{MARKER_END}\nafter"
    table = render_table(data)
    updated = replace_table(original, table)
    assert "OLD" not in updated
    assert table in updated
    assert updated.startswith("before")
    assert updated.endswith("after")
