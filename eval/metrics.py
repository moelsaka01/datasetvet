"""Metrics for the accuracy evaluation (PLAN.md section 8, task 4.6).

Usage:  python eval/metrics.py dev-grid        pick each scanner's thresholds (dev only)
        python eval/metrics.py test            one metrics set per configuration

Writes eval/results/metrics-<run>.json, and for the test run a disagreement sample per
configuration (eval/results/disagreements-<scanner>.csv) for the owner to label. Nothing
is pooled across configurations.
"""

from __future__ import annotations

import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
from build_key import licence_map

from datasetvet.licences import spdx

RES = ROOT / "eval" / "results"
EXPECTED = ["consistent", "inconsistent", "missing"]
OURS = ["consistent", "inconsistent", "missing", "unknown"]
SAMPLE = 30
SEED = 4


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    ea, eb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ea[c] * eb[c] for c in set(ea) | set(eb)) / (n * n)
    return None if pe == 1 else (po - pe) / (1 - pe)


def metrics(recs: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in recs if r.get("status")]
    excluded = Counter(r["excluded"].split(":")[0] for r in recs if not r.get("status"))
    matrix = {e: {o: 0 for o in OURS} for e in EXPECTED}
    for r in scored:
        matrix[r["expected"]][r["status"]] += 1
    decided = [r for r in scored if r["status"] != "unknown"]
    agree = sum(r["status"] == r["expected"] for r in decided)
    pred_inc = [r for r in scored if r["status"] == "inconsistent"]
    true_inc = [r for r in scored if r["expected"] == "inconsistent"]
    tp = sum(r["expected"] == "inconsistent" for r in pred_inc)
    q1 = [r for r in scored if r.get("q1_match") is not None]
    lo, hi = wilson(agree, len(decided))
    return {
        "rows": len(recs), "scored": len(scored), "excluded": dict(excluded),
        "confusion": matrix,
        "decided": len(decided), "agree": agree,
        "agreement_decided": agree / len(decided) if decided else None,
        "agreement_decided_wilson95": [lo, hi],
        "agreement_all_rows": agree / len(scored) if scored else None,
        "agreement_all_rows_wilson95": list(wilson(agree, len(scored))),
        "abstention": (len(scored) - len(decided)) / len(scored) if scored else None,
        "abstained": len(scored) - len(decided),
        "kappa_decided": kappa([(r["expected"], r["status"]) for r in decided]),
        "inconsistent_precision": tp / len(pred_inc) if pred_inc else None,
        "inconsistent_precision_n": [tp, len(pred_inc)],
        "inconsistent_recall": tp / len(true_inc) if true_inc else None,
        "inconsistent_recall_n": [tp, len(true_inc)],
        "q1_card_match": sum(r["q1_match"] for r in q1) / len(q1) if q1 else None,
        "q1_n": [sum(r["q1_match"] for r in q1), len(q1)],
        "q2": q2(scored),
        "drivers": drivers(scored),
    }


def q2(recs: list[dict[str, Any]]) -> dict[str, Any]:
    """Our licence for a GitHub source vs the DPI's recorded GitHub licence (same repo only
    when the DPI's GitHub URL is the source we read)."""
    lmap = licence_map()
    n = agree = unknown = 0
    for r in recs:
        gh = r.get("dpi_github_licence")
        if not gh or gh not in lmap or lmap[gh][0] != "spdx":
            continue
        want = lmap[gh][1]
        sides = [c for c in r.get("comparisons", []) if c["check"].startswith(
            "licence.source:github.com")]
        if not sides:
            continue
        n += 1
        found = {e for c in sides for e in (c["other"] or []) if isinstance(e, str)}
        if not found:
            unknown += 1
        elif any(spdx.relation(want, e).kind == "equivalent" for e in found):
            agree += 1
    return {"rows_with_github_source_and_dpi_licence": n, "agree": agree,
            "no_detection": unknown, "agreement": agree / n if n else None}


def drivers(recs: list[dict[str, Any]]) -> dict[str, int]:
    """Which comparison kinds gave our `inconsistent` statuses (a row can count twice)."""
    out: Counter[str] = Counter()
    for r in recs:
        if r["status"] != "inconsistent":
            continue
        for c in r.get("comparisons", []):
            if c["status"] == "inconsistent":
                k = c["check"]
                out["README text" if k == "licence.readme" else
                    "repo licence file" if k.startswith("licence.file:") else
                    "GitHub source" if "github.com" in k else
                    "HF dataset source" if "HF dataset" in k else "other source"] += 1
    return dict(out)


def posthoc_without_sources(recs: list[dict[str, Any]]) -> dict[str, Any]:
    """POST-HOC, exploratory (chosen after seeing the test results, not part of the frozen
    config): the same aggregation using only the card's own repo (README text and repo
    licence files), ignoring stated sources such as GitHub repos, whose LICENSE often covers
    code rather than data."""
    out = []
    for r in recs:
        if not r.get("status") or "comparisons" not in r:
            continue
        own = [c["status"] for c in r["comparisons"]
               if c["check"] == "licence.readme" or c["check"].startswith("licence.file:")]
        state = (r.get("c1") or {}).get("state", "")
        st = ("missing" if state == "missing" else "inconsistent" if "inconsistent" in own
              else "consistent" if "consistent" in own else "unknown")
        out.append(dict(r, status=st))
    m = metrics(out)
    return {k: m[k] for k in ("scored", "confusion", "decided", "agree", "agreement_decided",
                              "agreement_decided_wilson95", "abstention", "kappa_decided",
                              "inconsistent_precision_n", "inconsistent_recall_n")}


def pick(by_conf: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """config.yml's selection rule: most agreeing rows; ties go to the Phase 3 default."""
    defaults = {"builtin": "builtin dice=0.90 contain=0.95", "scancode": "scancode min_score=90"}
    best: dict[str, Any] = {}
    for scanner, default in defaults.items():
        cands = [(sum(r.get("status") == r["expected"] for r in recs), conf == default, conf)
                 for conf, recs in by_conf.items() if recs and recs[0]["scanner"] == scanner]
        if cands:
            best[scanner] = max(cands)[2]
    return best


def disagreements(conf: str, recs: list[dict[str, Any]]) -> None:
    bad = [r for r in recs if r.get("status") and r["status"] != r["expected"]]
    sample = random.Random(SEED).sample(bad, min(SAMPLE, len(bad)))
    name = recs[0]["scanner"]
    path = RES / f"disagreements-{name}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["hf_id", "revision", "expected", "ours", "card_c1", "comparisons",
                    "owner_label (ours wrong / key wrong / changed since audit / ambiguous)",
                    "notes"])
        for r in sorted(sample, key=lambda x: x["hf_id"].lower()):
            comps = "; ".join(f"{c['check']}={c['status']}"
                              + (f" [{', '.join(map(str, c['other']))}]"
                                 if isinstance(c.get("other"), list) and c["other"] else "")
                              for c in r.get("comparisons", []))
            w.writerow([r["hf_id"], (r["revision"].get("sha") or "")[:12], r["expected"],
                        r["status"], (r.get("c1") or {}).get("expression") or
                        (r.get("c1") or {}).get("state"), comps, "", ""])
    print(f"{conf}: {len(sample)} of {len(bad)} disagreements -> {path.name}")


def main(run: str) -> None:
    by_conf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in (RES / "runs" / f"{run}.jsonl").read_text("utf-8").splitlines():
        r = json.loads(line)
        by_conf[r["config"]].append(r)
    out = {conf: metrics(recs) for conf, recs in sorted(by_conf.items())}
    result: dict[str, Any] = {"run": run, "configurations": out}
    if run == "test":
        result["posthoc_without_sources"] = {conf: posthoc_without_sources(recs)
                                             for conf, recs in sorted(by_conf.items())}
    if run.endswith("grid"):
        result["selected"] = pick(by_conf)
    (RES / f"metrics-{run}.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    for conf, m in out.items():
        print(f"{conf:34s} agree {m['agree']:3d}/{m['scored']:3d} decided {m['decided']:3d} "
              f"acc_decided {m['agreement_decided'] or 0:.3f} abst {m['abstention'] or 0:.3f} "
              f"kappa {m['kappa_decided'] or 0:.3f}")
    if "selected" in result:
        print("selected:", result["selected"])
    if run == "test":
        for conf, recs in sorted(by_conf.items()):
            disagreements(conf, recs)


if __name__ == "__main__":
    main(sys.argv[1])
