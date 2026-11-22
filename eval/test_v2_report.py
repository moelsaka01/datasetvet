"""Phase 5.5: v2 on the old test split, NO LONGER BLIND (PLAN.md 8.1).

Usage:  python eval/test_v2_report.py     after `python eval/run_v2.py test`

Compares v2 (eval/results/runs/test-v2.jsonl) with v1's frozen built-in test run
(eval/results/runs/test.jsonl) on the same rows: the old test split as a whole, and the rows
not used in rule work (the 48 disagreement-sample datasets were). Same metrics as the held-out
scorer. Writes eval/results/metrics-test-v2.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

from evalmods import load

score = load("eval_holdout_score", "eval/holdout/score.py")
RUNS = ROOT / "eval" / "results" / "runs"
V1_CONFIG = "builtin dice=0.90 contain=0.95"


def rows(path: Path, config: str | None = None) -> dict[str, dict[str, Any]]:
    out = {}
    for line in path.read_text("utf-8").splitlines():
        r = json.loads(line)
        if (config is None or r["config"] == config) and r.get("status"):
            out[r["hf_id"]] = r
    return out


def compare(v1: dict[str, dict[str, Any]], v2: dict[str, dict[str, Any]],
            ids: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"rows": len(ids)}
    for name, run in (("v1", v1), ("v2", v2)):
        out[name] = score.config_metrics([(run[i]["expected"], run[i]["status"]) for i in ids])
    out["v2_vs_v1"] = score.mcnemar_exact([v2[i]["status"] == v2[i]["expected"] for i in ids],
                                          [v1[i]["status"] == v1[i]["expected"] for i in ids])
    out["v2_consistent_by_sub"] = {
        s: sum(1 for i in ids if v2[i]["status"] == "consistent"
               and v2[i].get("summary_sub") == s) for s in ("confirmed", "uncontradicted")}
    out["v2_uncontradicted_expected"] = {
        e: sum(1 for i in ids if v2[i].get("summary_sub") == "uncontradicted"
               and v2[i]["expected"] == e) for e in ("consistent", "inconsistent")}
    return out


def main() -> int:
    v1 = rows(RUNS / "test.jsonl", V1_CONFIG)
    v2 = rows(RUNS / "test-v2.jsonl")
    rulework = {json.loads(x)["hf_id"] for x in (RUNS / "rulework-v2.jsonl").read_text(
        "utf-8").splitlines() if json.loads(x)["group"] == "audited"}
    both = sorted(set(v1) & set(v2))
    result = {"note": "old test split, no longer blind: looked at in Phase 4 and Phase 5, and "
                      "48 of its datasets were used in Phase 5.5 rule work",
              "only_in_v1": sorted(set(v1) - set(v2)), "only_in_v2": sorted(set(v2) - set(v1)),
              "all": compare(v1, v2, both),
              "not_used_in_rule_work": compare(v1, v2, [i for i in both if i not in rulework])}
    (ROOT / "eval" / "results" / "metrics-test-v2.json").write_text(
        json.dumps(result, indent=1) + "\n", "utf-8")
    for part in ("all", "not_used_in_rule_work"):
        r = result[part]
        for name in ("v1", "v2"):
            m = r[name]
            print(f"{part:22s} {name}: agree {m['agree']}/{m['scored']} "
                  f"(decided {m['agreement_decided']:.3f}) abst {m['abstention']:.3f} "
                  f"kappa {m['kappa_decided']:.3f} "
                  f"{m['kappa_decided_bootstrap']['ci95']}")
        print(f"{'':22s} v2 vs v1: {r['v2_vs_v1']}  {r['v2_consistent_by_sub']} "
              f"{r['v2_uncontradicted_expected']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
