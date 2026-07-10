import asyncio
import json
import time

from ..multistage import process_meaning, run_stage1_extraction
from ..utils import FLASH_MODEL, MetricsTracker


async def run_pipeline(word="hana", salt=None, timeout=120):
    """Sequential multi-stage baseline without explicit thinking controls."""
    metrics = MetricsTracker()
    e2e_start = time.time()

    base_data = await run_stage1_extraction(word, salt, timeout, metrics, label="Pipeline")

    final_entry = []
    for idx, meaning in enumerate(base_data["meanings"], start=1):
        result = await process_meaning(word, meaning, idx, salt, timeout, metrics, label="Pipeline")
        final_entry.append(result)

    summary = metrics.summary()
    summary["e2e_duration"] = time.time() - e2e_start
    summary["mode"] = "pipeline"
    summary["model"] = FLASH_MODEL
    return final_entry, summary


if __name__ == "__main__":
    import sys

    word = sys.argv[1] if len(sys.argv) > 1 else "hana"
    result, metrics = asyncio.run(run_pipeline(word))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
