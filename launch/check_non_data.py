"""Which launch-scan Tier B datasets read a file that is no longer treated as data (Phase 4.5).

Usage:  python launch/check_non_data.py LIST

The first scan read every Parquet/CSV/JSON file of a repo whose card names no data files
(`configs`), including tokenizer and config JSON and dependency folders. Since Phase 4.5 those
files are skipped (`is_non_data_path`). That changes a dataset's rows even when the file read
without an error, so the old "corrupt" check does not find every affected dataset.

For each Tier B dataset that the first scan read from original files, this re-plans the data
files with the current code (anonymous API calls only: dataset info, README, no data) and
lists the datasets for which `is_non_data_path` skips at least one file the old planner would
have read. Writes launch/results/non-data-check.json. It changes no state row and no report.
Datasets whose listing was cut off are not re-planned here: they are rescanned anyway.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REPORTS = ROOT / "launch" / "results" / "reports-first-scan"
RESULTS = ROOT / "launch" / "results"
OUT = RESULTS / "non-data-check.json"


def main(list_path: Path) -> None:
    from datasetvet.config import default_cache_dir
    from datasetvet.http import Http
    from datasetvet.hubs.huggingface import (
        HuggingFaceAdapter,
        configs_mapping,
        file_format,
        is_non_data_path,
    )

    frozen = {d["id"]: d for d in json.loads(list_path.read_text("utf-8"))["datasets"]}
    cut = set(json.loads((RESULTS / "listing-truncated.json").read_text("utf-8"))["truncated"])
    todo = []
    for p in sorted((REPORTS / "B").glob("*.json")):
        rep = json.loads(p.read_text("utf-8"))
        ds_id = rep["dataset"]["id"]
        if (rep.get("scan") or {}).get("source") == "original files" and ds_id not in cut:
            todo.append(ds_id)
    http = Http(default_cache_dir(), host_interval=1.0)
    hf = HuggingFaceAdapter(http)
    out: dict[str, Any] = {"checked": len(todo), "affected": {}, "errors": {}}
    try:
        for i, ds_id in enumerate(todo, 1):
            try:
                ds = hf.resolve(f"hf:{ds_id}@{frozen[ds_id]['sha']}")
                card = hf.card(ds)
                files = [f.path for f in hf.files(ds) if f.path != "README.md"
                         and not any(part.startswith(".") for part in f.path.split("/"))
                         and file_format(f.path)]
                if configs_mapping(card.metadata.get("configs"), files):
                    continue  # the card names its data files: nothing is skipped
                skipped = sorted(p for p in files if is_non_data_path(p))
                if skipped:
                    out["affected"][ds_id] = {"skipped": len(skipped), "examples": skipped[:5]}
            except Exception as exc:  # noqa: BLE001  one dataset must not stop the check
                out["errors"][ds_id] = f"{type(exc).__name__}: {exc}"[:200]
            if i % 20 == 0:
                print(f"{i}/{len(todo)}", flush=True)
    finally:
        http.close()
    OUT.write_text(json.dumps(out, indent=1) + "\n", "utf-8")
    print(f"{len(out['affected'])} of {len(todo)} original-file datasets read files that are "
          f"now skipped; {len(out['errors'])} errors -> {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
