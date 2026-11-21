"""Which launch-scan rows the Phase 4.5 fixes can change (RESULTS.md section 2).

Usage:  python launch/rescan_set.py LIST

Reads the first scan (launch/results/reports-first-scan/, launch/first-scan-state.sqlite,
launch/results/listing-truncated.json and, if present, listing-truncated-all.json) and writes
launch/results/rescan-set.json: for each tier the dataset ids to run again, and why. A dataset
is in the set only if one of the fixes applies to what the first scan recorded for it:

  B  listing-cut-off      read from original files, and the Hub's file list had 100,000 entries
  B  nanosecond-timestamp failed with a nanosecond timestamp ValueError
  B  arrow-index-error    failed with ArrowIndexError (pyarrow's JSON reader)
  B  json-array-of-non-objects  a file failed with "'str'/'list'/... has no attribute 'keys'"
  B  unreadable-files     the old "corrupt" check found a file it could not read (so the
                          check, which is renamed and no longer counts non-data files, differs)
  B  non-data-files-skipped  the scan read a tokenizer/config/dependency file that is now
                          skipped, even if it read without error (launch/check_non_data.py)
  A  listing-cut-off      the card has missing-file link results and the file list was cut off
                          (with listing-truncated-all.json: any Tier A dataset whose file list
                          was cut off, because licence files are searched in that list too)

Every other row is left as it is: a Parquet-conversion scan, a card, a licence comparison or a
link check does not depend on anything that changed. It changes no state row and no report.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "launch" / "results"
REPORTS = RESULTS / "reports-first-scan"
STATE = ROOT / "launch" / "first-scan-state.sqlite"
OUT = RESULTS / "rescan-set.json"
NON_OBJECT_ERRORS = ("object has no attribute 'keys'",)


def add(reasons: dict[str, dict[str, list[str]]], tier: str, ds: str, why: str) -> None:
    reasons.setdefault(tier, {}).setdefault(ds, [])
    if why not in reasons[tier][ds]:
        reasons[tier][ds].append(why)


def main(list_path: Path) -> None:
    frozen = {d["id"] for d in json.loads(list_path.read_text("utf-8"))["datasets"]}
    reasons: dict[str, dict[str, list[str]]] = {"A": {}, "B": {}}

    cut = json.loads((RESULTS / "listing-truncated.json").read_text("utf-8"))
    for ds, row in cut["datasets"].items():
        if row.get("truncated") and "tier_B_scan" in row:
            add(reasons, "B", ds, "listing-cut-off")
        if row.get("truncated") and row.get("tier_A_missing_file_results"):
            add(reasons, "A", ds, "listing-cut-off")
    extra = RESULTS / "listing-truncated-all.json"
    if extra.exists():
        for ds in json.loads(extra.read_text("utf-8"))["truncated"]:
            add(reasons, "A", ds, "listing-cut-off")

    nd = RESULTS / "non-data-check.json"
    if nd.exists():
        for ds in json.loads(nd.read_text("utf-8"))["affected"]:
            add(reasons, "B", ds, "non-data-files-skipped")

    db = sqlite3.connect(STATE)
    for ds, err in db.execute("SELECT dataset_id, error FROM runs WHERE tier='B' "
                              "AND status='failed'"):
        err = err or ""
        if "Nanosecond resolution" in err:
            add(reasons, "B", ds, "nanosecond-timestamp")
        elif err.startswith("ArrowIndexError"):
            add(reasons, "B", ds, "arrow-index-error")
    db.close()

    for p in sorted((REPORTS / "B").glob("*.json")):
        rep = json.loads(p.read_text("utf-8"))
        ds = rep["dataset"]["id"]
        for r in rep["results"]:
            if r["check"] != "health.corrupt" or r["status"] != "found":
                continue
            add(reasons, "B", ds, "unreadable-files")
            if any(m in (f.get("data") or {}).get("error", "") for f in r["facts"]
                   for m in NON_OBJECT_ERRORS):
                add(reasons, "B", ds, "json-array-of-non-objects")

    out = {"list": list_path.name,
           "A": sorted(reasons["A"]), "B": sorted(reasons["B"]),
           "reasons": {t: dict(sorted(v.items())) for t, v in reasons.items()}}
    unknown = (set(out["A"]) | set(out["B"])) - frozen
    assert not unknown, unknown
    OUT.write_text(json.dumps(out, indent=1) + "\n", "utf-8")
    for tier in "AB":
        by_reason: dict[str, int] = {}
        for rs in reasons[tier].values():
            for why in rs:
                by_reason[why] = by_reason.get(why, 0) + 1
        print(f"tier {tier}: {len(reasons[tier])} datasets  {by_reason}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
