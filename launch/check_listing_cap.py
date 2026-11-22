"""Which launch-scan datasets had a file listing cut off by the Hub (RESULTS.md section 2).

Usage:  python launch/check_listing_cap.py LIST [--all]

The Hub's dataset API (`/api/datasets/{id}/revision/{sha}`) returns at most 100,000 entries
in `siblings`. datasetvet's HF adapter (at commit cdb210e and before) takes the repo's file
list from there, so for a larger repo it sees only part of the files:
- Tier A: a card's `configs[].data_files` path can match a file the list left out and is then
  reported as a "missing file";
- Tier B: when data health reads the original files (no Parquet conversion), it reads only
  files from that partial list, so even a scan labelled "Full scan" is not one.

For each dataset this script re-reads `siblings` at the frozen sha (one anonymous API call,
through datasetvet's rate-limited Http) for every Tier A report with a missing-file result
and every Tier B report read from original files, and writes
launch/results/listing-truncated.json. It changes no state row and no report.

`--all` (Phase 4.5) checks every dataset in LIST instead, because a Tier A licence-file search
also used the cut-off list, and writes launch/results/listing-truncated-all.json. The fix for
the cut-off itself is in the HF adapter (`HuggingFaceAdapter.listing`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REPORTS = ROOT / "launch" / "results" / "reports-first-scan"
OUT = ROOT / "launch" / "results" / "listing-truncated.json"
OUT_ALL = ROOT / "launch" / "results" / "listing-truncated-all.json"
LISTING_CAP = 100_000


def missing_files(rep: dict) -> int:
    return sum(1 for r in rep["results"] if r["family"] == "links" and r["status"] == "dead"
               and r["facts"] and "(missing file)" in r["facts"][0]["text"])


def main(list_path: Path, check_all: bool = False) -> None:
    from datasetvet.config import default_cache_dir
    from datasetvet.http import Http

    frozen = {d["id"]: d for d in json.loads(list_path.read_text("utf-8"))["datasets"]}
    want: dict[str, dict] = {}
    if check_all:
        want = {i: {} for i in frozen}
    else:
        for p in sorted((REPORTS / "A").glob("*.json")):
            rep = json.loads(p.read_text("utf-8"))
            n = missing_files(rep)
            if n:
                want.setdefault(rep["dataset"]["id"], {})["tier_A_missing_file_results"] = n
        for p in sorted((REPORTS / "B").glob("*.json")):
            rep = json.loads(p.read_text("utf-8"))
            scan = rep.get("scan") or {}
            if scan.get("source") == "original files":
                want.setdefault(rep["dataset"]["id"], {})["tier_B_scan"] = scan.get("kind")
    http = Http(default_cache_dir(), host_interval=1.0)
    try:
        for i, row in want.items():
            sha = frozen[i]["sha"]
            r = http.get(f"https://huggingface.co/api/datasets/{i}/revision/{sha}")
            row["siblings"] = len(r.json().get("siblings", [])) if r.ok else None
            row["truncated"] = row["siblings"] is not None and row["siblings"] >= LISTING_CAP
    finally:
        http.close()
    out: dict[str, Any] = {"listing_cap": LISTING_CAP, "checked": len(want),
                           "truncated": sorted(i for i, r in want.items() if r["truncated"]),
                           "datasets": dict(sorted(want.items()))}
    target = OUT_ALL if check_all else OUT
    target.write_text(json.dumps(out, indent=1) + "\n", "utf-8")
    print(f"{len(out['truncated'])} of {len(want)} checked datasets have a listing of "
          f"{LISTING_CAP:,} files -> {target}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), "--all" in sys.argv[2:])
