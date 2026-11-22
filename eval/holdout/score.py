"""Phase 5.5, step 4: metrics for A, B and C on the held-out rows (PLAN.md 8.1).

Usage:  python eval/holdout/score.py      after eval/holdout/predict.py

Reads eval/results/holdout/predictions.jsonl and writes eval/results/holdout/metrics.json.
Per configuration (never pooled): the 3x4 confusion matrix; agreement on decided rows, over all
scored rows (abstaining = miss) and abstention, each with a Wilson 95% interval; Cohen's kappa
on decided rows with a percentile bootstrap 95% interval (10,000 resamples of the scored rows,
seed 0); kappa over all scored rows with `unknown` as a fourth category; `inconsistent`
precision and recall. Paired: exact two-sided McNemar on per-row correctness, C vs A and C vs B.
The goal (kappa >= 0.61, abstention < 15%, C beats A and B with p < 0.05) is checked as written.
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from metrics import kappa, wilson  # eval/metrics.py

RES = ROOT / "eval" / "results" / "holdout"
EXPECTED = ["consistent", "inconsistent", "missing"]
OURS = ["consistent", "inconsistent", "missing", "unknown"]
CONFIGS = ["A", "B", "C"]
BOOT_N, BOOT_SEED = 10_000, 0
GOAL = {"kappa_min": 0.61, "abstention_below": 0.15, "alpha": 0.05}


def mcnemar_exact(x_right: Sequence[bool], y_right: Sequence[bool]) -> dict[str, Any]:
    """Exact two-sided McNemar: binomial test on the discordant pairs."""
    b = sum(x and not y for x, y in zip(x_right, y_right, strict=True))
    c = sum(y and not x for x, y in zip(x_right, y_right, strict=True))
    n = b + c
    if n == 0:
        return {"x_only": b, "y_only": c, "p": 1.0}
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {"x_only": b, "y_only": c, "p": min(1.0, 2 * tail)}


def kappa_decided(pairs: list[tuple[str, str]]) -> float | None:
    return kappa([(e, o) for e, o in pairs if o != "unknown"])


def bootstrap_kappa(pairs: list[tuple[str, str]], n: int = BOOT_N, seed: int = BOOT_SEED
                    ) -> dict[str, Any]:
    rng = random.Random(seed)
    vals = []
    undefined = 0
    for _ in range(n):
        k = kappa_decided([pairs[rng.randrange(len(pairs))] for _ in pairs])
        if k is None:
            undefined += 1
        else:
            vals.append(k)
    if not vals:
        return {"ci95": None, "undefined_resamples": undefined}
    vals.sort()
    lo = vals[int(0.025 * (len(vals) - 1))]
    hi = vals[int(0.975 * (len(vals) - 1))]
    return {"ci95": [lo, hi], "undefined_resamples": undefined}


def config_metrics(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    n = len(pairs)
    matrix = {e: {o: 0 for o in OURS} for e in EXPECTED}
    for e, o in pairs:
        matrix[e][o] += 1
    decided = [(e, o) for e, o in pairs if o != "unknown"]
    agree = sum(e == o for e, o in decided)
    pred_inc = [e for e, o in pairs if o == "inconsistent"]
    true_inc = [o for e, o in pairs if e == "inconsistent"]
    tp = sum(e == "inconsistent" for e in pred_inc)
    abst = n - len(decided)
    return {
        "scored": n, "confusion": matrix, "decided": len(decided), "agree": agree,
        "agreement_decided": agree / len(decided) if decided else None,
        "agreement_decided_wilson95": list(wilson(agree, len(decided))),
        "agreement_all_rows": agree / n if n else None,
        "agreement_all_rows_wilson95": list(wilson(agree, n)),
        "abstained": abst, "abstention": abst / n if n else None,
        "abstention_wilson95": list(wilson(abst, n)),
        "kappa_decided": kappa_decided(pairs),
        "kappa_decided_bootstrap": bootstrap_kappa(pairs) if n else None,
        "kappa_all_rows_unknown_as_category": kappa(pairs),
        "inconsistent_precision_n": [tp, len(pred_inc)],
        "inconsistent_recall_n": [tp, len(true_inc)],
    }


def score(preds: list[dict[str, Any]]) -> dict[str, Any]:
    excluded: dict[str, int] = {}
    scored = []
    for p in preds:
        why = None
        if p["expected"] not in EXPECTED:
            why = p["expected"]
        elif p.get("excluded"):
            why = "card not readable at the frozen sha (scoring run)"
        if why:
            excluded[why] = excluded.get(why, 0) + 1
        else:
            scored.append(p)
    out: dict[str, Any] = {"rows": len(preds), "scored": len(scored), "excluded": excluded,
                           "batches": sorted({p["batch"] for p in preds})}
    right = {c: [p[c] == p["expected"] for p in scored] for c in CONFIGS}
    out["configurations"] = {c: config_metrics([(p["expected"], p[c]) for p in scored])
                             for c in CONFIGS}
    out["paired"] = {f"C vs {x}": mcnemar_exact(right["C"], right[x]) for x in ("A", "B")}
    c = out["configurations"]["C"]
    k = c["kappa_decided"]
    beats = {x: (sum(right["C"]) > sum(right[x])
                 and out["paired"][f"C vs {x}"]["p"] < GOAL["alpha"]) for x in ("A", "B")}
    out["goal"] = {
        "kappa_decided_at_least_0.61": k is not None and k >= GOAL["kappa_min"],
        "abstention_below_15pct": c["abstention"] is not None
        and c["abstention"] < GOAL["abstention_below"],
        "beats_A": beats["A"], "beats_B": beats["B"],
    }
    out["goal"]["met"] = all(out["goal"].values())
    out["C_consistent_by_sub"] = {
        s: sum(1 for p in scored if p["C"] == "consistent" and p.get("C_sub") == s)
        for s in ("confirmed", "uncontradicted")}
    out["C_uncontradicted_agree"] = sum(1 for p in scored if p.get("C_sub") == "uncontradicted"
                                        and p["expected"] == "consistent")
    out["too_few_rows"] = len(scored) < 60
    return out


def main() -> int:
    preds = [json.loads(x) for x in (RES / "predictions.jsonl").read_text("utf-8").splitlines()]
    result = score(preds)
    (RES / "metrics.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    for name, m in result["configurations"].items():
        print(f"{name}: agree {m['agree']}/{m['scored']} decided {m['decided']} "
              f"kappa {m['kappa_decided']} abst {m['abstention']}")
    print("paired:", result["paired"])
    print("goal:", result["goal"])
    if result["too_few_rows"]:
        print("fewer than 60 scored rows: PLAN.md 8.1 says draw batch b before scoring")
    return 0


if __name__ == "__main__":
    sys.exit(main())
