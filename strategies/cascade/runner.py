import asyncio
import json
import time
from datetime import datetime

from ..multistage import process_meaning, run_stage1_extraction
from ..utils import FLASH_MODEL, MetricsTracker


async def run_cascade(word: str = "hana", salt: str = None, timeout: float = 120.0):
    metrics = MetricsTracker()
    e2e_start = time.time()

    base_data = await run_stage1_extraction(
        word, salt, timeout, metrics, label="Cascade", thinking_level="LOW"
    )

    # return_exceptions=True: el fallo de una acepcion NO debe cancelar a las
    # corrutinas hermanas en vuelo ni tirar toda la palabra (H5). Cada resultado
    # se inspecciona por separado; las acepciones que fallaron se descartan del
    # entry final (Stage 2 no tiene fallback util) y se loguean.
    results = await asyncio.gather(
        *(
            process_meaning(
                word,
                meaning,
                idx,
                salt,
                timeout,
                metrics,
                label="Cascade",
                thinking_level_stage2="LOW",
                thinking_level_stage3="MINIMAL",
            )
            for idx, meaning in enumerate(base_data["meanings"], start=1)
        ),
        return_exceptions=True,
    )

    final_entry = []
    for idx, result in enumerate(results, start=1):
        if isinstance(result, Exception):
            print(
                f"      [{datetime.now().strftime('%H:%M:%S')}] [Cascade] "
                f"Meaning {idx} failed, skipped: {str(result) or type(result).__name__}"
            )
            continue
        final_entry.append(result)

    summary = metrics.summary()
    summary["e2e_duration"] = time.time() - e2e_start
    summary["mode"] = "cascade"
    summary["model"] = FLASH_MODEL
    return final_entry, summary


if __name__ == "__main__":
    import sys

    word = sys.argv[1] if len(sys.argv) > 1 else "hana"
    result, metrics = asyncio.run(run_cascade(word))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
