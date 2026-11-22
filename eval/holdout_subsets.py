"""Phase 5.5: held-out metrics on subsets, NOT pre-registered (exploratory).

Usage:  python eval/holdout_subsets.py     after eval/holdout/score.py

Uses the frozen scorer's metric code (eval/holdout/score.py) on:
- rows the owner marked `confidence = sure` (asked for by the owner after labelling);
- rows whose final label equals the AI first pass's label (status and expert licences), and
  rows where the owner changed it, when the first-pass file is given:
    python eval/holdout_subsets.py --first-pass PATH
Writes eval/results/holdout/metrics-subsets.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

from evalmods import load

score = load("eval_holdout_score", "eval/holdout/score.py")
RES = ROOT / "eval" / "results" / "holdout"


def lic(s: str) -> frozenset[str]:
    return frozenset(t.strip().lower() for t in re.split(r"[;,]", s or "") if t.strip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first-pass", type=Path, default=None)
    args = ap.parse_args(argv)
    preds = [json.loads(x) for x in (RES / "predictions.jsonl").read_text("utf-8").splitlines()]
    with open(ROOT / "eval" / "holdout" / "sheet.csv", encoding="utf-8") as fh:
        sheet = {r["hf_id"]: r for r in csv.DictReader(fh)}
    subsets: dict[str, list[dict[str, Any]]] = {
        "confidence_sure": [p for p in preds if sheet[p["hf_id"]]["confidence"] == "sure"],
        "confidence_unsure": [p for p in preds if sheet[p["hf_id"]]["confidence"] != "sure"]}
    if args.first_pass:
        with open(args.first_pass, encoding="utf-8-sig") as fh:
            ai = {r["hf_id"]: r for r in csv.DictReader(fh)}

        def same(i: str) -> bool:
            return (ai[i]["expected_status"].strip() == sheet[i]["expected_status"].strip()
                    and lic(ai[i]["expert_licences"]) == lic(sheet[i]["expert_licences"]))

        subsets["unchanged_from_first_pass"] = [p for p in preds if same(p["hf_id"])]
        subsets["changed_by_owner"] = [p for p in preds if not same(p["hf_id"])]
    out = {"note": "exploratory, not pre-registered"}
    for name, rows in subsets.items():
        r = score.score(rows)
        out[name] = {k: r[k] for k in ("rows", "scored", "excluded", "configurations",
                                       "paired", "goal")}
        print(name, "scored", r["scored"])
        for c, m in r["configurations"].items():
            print(f"  {c}: agree {m['agree']}/{m['scored']} abst {m['abstention']} "
                  f"kappa {m['kappa_decided']}")
        print("  paired", r["paired"])
    (RES / "metrics-subsets.json").write_text(json.dumps(out, indent=1) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
