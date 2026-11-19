"""Summarise the launch scan (PLAN.md section 10, task 4.7).

Usage:  python launch/summarize.py LIST

Reads launch/state.sqlite and writes:
- launch/results/datasets.csv: one row per listed dataset, facts only (statuses and counts);
- launch/results/summary.json: counts of each status per check, with Wilson 95% intervals
  for the shares quoted in RESULTS.md.
No dataset is called good or bad: the table states what each check found.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "launch"))
from state import State

OUT = ROOT / "launch" / "results"


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if not n:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def share(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, "share": round(k / n, 4) if n else None, "wilson95": wilson(k, n)}


def tier_a(rep: dict[str, Any]) -> dict[str, Any]:
    res = rep["results"]
    card = next((r for r in res if r["check"] == "card.licence"), None)
    lic = [r for r in res if r["family"] == "licence"]
    prov = [r for r in res if r["family"] == "provenance"]
    links = [r for r in res if r["family"] == "links"]
    lc = Counter(r["status"] for r in lic)
    pc = Counter(r["status"] for r in prov)
    kc = Counter(r["status"] for r in links)
    licence_values = ""
    if card:
        for f in card["facts"]:
            licence_values = f.get("text", "")[:120]
            break
    return {
        "gated": rep["dataset"].get("gated") or False,
        "card_licence": card["status"] if card else "",
        "card_licence_fact": licence_values,
        "licence_comparisons": sum(lc.values()),
        **{f"licence_{s}": lc.get(s, 0) for s in ("consistent", "inconsistent", "missing",
                                                  "unknown")},
        "provenance_comparisons": sum(pc.values()),
        **{f"provenance_{s}": pc.get(s, 0) for s in ("consistent", "inconsistent", "missing",
                                                     "unknown")},
        "links": sum(kc.values()),
        **{f"links_{s}": kc.get(s, 0) for s in ("ok", "dead", "restricted", "unreachable",
                                                "unknown")},
        "card_fields_missing": ";".join(sorted(r["check"].split(".", 1)[1] for r in res
                                                if r["family"] == "card"
                                                and r["status"] == "missing")),
    }


def tier_b(rep: dict[str, Any]) -> dict[str, Any]:
    scan = rep.get("scan") or {}
    res = {r["check"]: r for r in rep["results"] if r["family"] == "health"}
    out = {"scan": scan.get("kind", ""), "rows_scanned": scan.get("rows_scanned"),
           "rows_total": scan.get("rows_total"), "bytes_total": scan.get("bytes_total"),
           "bytes_read": scan.get("bytes_read"), "scan_seconds": scan.get("seconds"),
           "scan_reason": (scan.get("reason") or "")[:200],
           "download_capped": "download cap reached" in (scan.get("reason") or "")}
    for k in ("duplicates", "leakage", "empty", "corrupt", "labels", "pii"):
        r = res.get(f"health.{k}")
        out[k] = r["status"] if r else ""
    return out


def main(list_path: Path) -> None:
    frozen = json.loads(list_path.read_text("utf-8"))
    state = State(ROOT / "launch" / "state.sqlite")
    rows = {}
    for d in frozen["datasets"]:
        rows[d["id"]] = {"rank": d["rank"], "id": d["id"], "downloads_30d": d["downloads_30d"],
                         "sha": (d.get("sha") or "")[:12],
                         "bytes_parquet": d.get("bytes_parquet")}
    errors: dict[str, Counter[str]] = {"A": Counter(), "B": Counter()}
    for tier, fn in (("A", tier_a), ("B", tier_b)):
        for r in state.rows(tier):
            if r["dataset_id"] not in rows:
                continue
            row = rows[r["dataset_id"]]
            row[f"tier_{tier}"] = r["status"]
            if r["status"] == "done":
                row.update(fn(json.loads(r["report"])))
            else:
                errors[tier][(r["error"] or "").split(":")[0]] += 1
                row[f"tier_{tier}_error"] = (r["error"] or "")[:160]
    state.close()
    table = sorted(rows.values(), key=lambda x: x["rank"])
    OUT.mkdir(parents=True, exist_ok=True)
    cols: list[str] = []
    for r in table:
        cols += [c for c in r if c not in cols]
    with open(OUT / "datasets.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(table)

    a = [r for r in table if r.get("tier_A") == "done"]
    b = [r for r in table if r.get("tier_B") == "done"]
    with_cmp = [r for r in a if r["licence_comparisons"]]
    scanned = [r for r in b if r["scan"] in ("full", "sampled")]
    summary = {
        "listed": len(table),
        "tier_A": {
            "done": len(a), "failed": sum(r.get("tier_A") == "failed" for r in table),
            "errors": dict(errors["A"]),
            "gated": sum(bool(r["gated"]) for r in a),
            "card_licence": dict(Counter(r["card_licence"] for r in a)),
            "with_any_licence_comparison": len(with_cmp),
            "licence_any_inconsistent": share(sum(r["licence_inconsistent"] > 0
                                                  for r in with_cmp), len(with_cmp)),
            "licence_any_consistent_none_inconsistent": share(sum(
                r["licence_consistent"] > 0 and r["licence_inconsistent"] == 0
                for r in with_cmp), len(with_cmp)),
            "licence_comparison_statuses": {s: sum(r[f"licence_{s}"] for r in a) for s in
                                            ("consistent", "inconsistent", "missing",
                                             "unknown")},
            "with_declared_parents": sum(r["provenance_comparisons"] > 0 for r in a),
            "provenance_any_inconsistent": sum(r["provenance_inconsistent"] > 0 for r in a),
            "provenance_statuses": {s: sum(r[f"provenance_{s}"] for r in a) for s in
                                    ("consistent", "inconsistent", "missing", "unknown")},
            "links_checked": sum(r["links"] for r in a),
            "link_statuses": {s: sum(r[f"links_{s}"] for r in a) for s in
                              ("ok", "dead", "restricted", "unreachable", "unknown")},
            "datasets_with_dead_link": share(sum(r["links_dead"] > 0 for r in a),
                                             sum(r["links"] > 0 for r in a)),
        },
        "tier_B": {
            "done": len(b), "failed": sum(r.get("tier_B") == "failed" for r in table),
            "errors": dict(errors["B"]),
            "scan_kind": dict(Counter(r["scan"] for r in b)),
            "download_capped": sum(bool(r["download_capped"]) for r in b),
            "bytes_read_total": sum(r["bytes_read"] or 0 for r in b),
            "rows_scanned_total": sum(r["rows_scanned"] or 0 for r in b),
            **{k: {"found": share(sum(r[k] == "found" for r in scanned),
                                  sum(r[k] in ("found", "none found") for r in scanned)),
                   "statuses": dict(Counter(r[k] for r in b))}
               for k in ("duplicates", "leakage", "empty", "corrupt", "pii")},
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", "utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
