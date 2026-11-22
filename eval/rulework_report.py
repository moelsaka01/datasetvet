"""Phase 5.5 rule work: one line per rule variant on the rule-work rows (PLAN.md 8.1).

Usage:  python eval/rulework_report.py     reads eval/results/runs/rulework-v2.jsonl

Selection rule (pre-registered): keep a rule when it raises the number of rule-work rows that
agree with the key, abstaining counted as a miss. Kappa and abstention are shown, not used.
Writes eval/results/metrics-rulework-v2.json.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

from metrics import metrics  # eval/metrics.py

RUN = ROOT / "eval" / "results" / "runs" / "rulework-v2.jsonl"
OUT = ROOT / "eval" / "results" / "metrics-rulework-v2.json"


def main() -> int:
    by: dict[str, list[dict]] = defaultdict(list)
    for line in RUN.read_text("utf-8").splitlines():
        r = json.loads(line)
        by[r["config"]].append(r)
    result = {}
    print(f"{'variant':26s} {'group':8s} agree/scored  decided  agree_dec  abst   kappa")
    for conf, recs in by.items():
        result[conf] = {}
        for group in ("all", "dev", "audited"):
            rs = [r for r in recs if group == "all" or r["group"] == group]
            m = metrics(rs)
            keep = {k: m[k] for k in ("scored", "agree", "decided", "agreement_decided",
                                      "agreement_decided_wilson95", "abstention",
                                      "kappa_decided", "confusion", "inconsistent_precision_n",
                                      "inconsistent_recall_n")}
            result[conf][group] = keep
            print(f"{conf:26s} {group:8s} {m['agree']:3d}/{m['scored']:3d}     "
                  f"{m['decided']:3d}      {m['agreement_decided'] or 0:.3f}    "
                  f"{m['abstention'] or 0:.3f}  {m['kappa_decided'] or 0:.3f}")
    OUT.write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
