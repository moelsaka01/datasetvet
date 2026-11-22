"""Summarise the launch scan (PLAN.md section 10, task 4.7).

Usage:  python launch/summarize.py LIST

Reads launch/state.sqlite and writes:
- launch/results/datasets.csv: one row per listed dataset, facts only (statuses and counts);
- launch/results/summary.json: counts of each status per check, with Wilson 95% intervals
  for the shares quoted in RESULTS.md, and the config hash(es) the rows were made with.
No dataset is called good or bad: the table states what each check found.

Phase 4.5: the state holds the first scan (config hashes FIRST_SCAN_HASHES, made before the
fixes) for every row the fixes cannot change, and a rescan under a new config hash for the rows
in launch/results/rescan-set.json. A row is marked `rescanned_A` / `rescanned_B` when its hash
is not the first scan's. The first scan's own summary is kept in launch/results/first-scan/.
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
# The config hashes of the first scan (before the Phase 4.5 fixes).
FIRST_SCAN_HASHES = {"A": "d0b085a50bef68aa", "B": "2472d09329f26eb6"}


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
    lic = [r for r in res if r["family"] == "licence" and r["check"] != "licence.summary"]
    overall = next((r for r in res if r["check"] == "licence.summary"), None)  # v2 (Phase 5.5)
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
        "licence_overall": overall["status"] if overall else "",
        "licence_overall_sub": ((overall.get("data") or {}).get("sub") or "") if overall else "",
        "licence_comparisons": sum(lc.values()),
        **{f"licence_{s}": lc.get(s, 0) for s in ("consistent", "inconsistent", "missing",
                                                  "unknown")},
        "provenance_comparisons": sum(pc.values()),
        **{f"provenance_{s}": pc.get(s, 0) for s in ("consistent", "inconsistent", "missing",
                                                     "unknown")},
        "links": sum(kc.values()),
        "links_missing_file": sum(1 for r in links if r["status"] == "dead" and r["facts"]
                                  and "(missing file)" in r["facts"][0]["text"]),
        **{f"links_{s}": kc.get(s, 0) for s in ("ok", "dead", "restricted", "unreachable",
                                                "unknown")},
        "card_fields_missing": ";".join(sorted(r["check"].split(".", 1)[1] for r in res
                                                if r["family"] == "card"
                                                and r["status"] == "missing")),
        # a missing-file result is never made from a cut-off list; this says it was not checked
        "file_list_incomplete": any("file list is incomplete" in n for n in
                                    rep.get("not_checked", [])),
    }


def tier_b(rep: dict[str, Any]) -> dict[str, Any]:
    scan = rep.get("scan") or {}
    res = {r["check"]: r for r in rep["results"] if r["family"] == "health"}
    out = {"scan": scan.get("kind", ""), "rows_scanned": scan.get("rows_scanned"),
           "rows_total": scan.get("rows_total"), "bytes_total": scan.get("bytes_total"),
           "bytes_read": scan.get("bytes_read"), "scan_seconds": scan.get("seconds"),
           "scan_reason": (scan.get("reason") or "")[:200],
           "download_capped": "download cap reached" in (scan.get("reason") or ""),
           "scan_source": scan.get("source") or "",
           # reports from before the field existed had it implicitly true
           "listing_complete": scan.get("listing_complete", True)}
    fetch = (rep.get("settings") or {}).get("data_fetch") or {}
    out["fetch_git"] = str(fetch.get("git", "")).split(":")[0]
    out["fetch_git_files"] = fetch.get("git_files", 0)
    out["fetch_http_files"] = fetch.get("http_files", 0)
    for k in ("duplicates", "leakage", "empty", "labels", "pii"):
        r = res.get(f"health.{k}")
        out[k] = r["status"] if r else ""
    # "health.corrupt" is the first scan's name for the check now called health.unreadable
    r = res.get("health.unreadable") or res.get("health.corrupt")
    out["unreadable"] = r["status"] if r else ""
    kinds = Counter((f.get("data") or {}).get("kind", "unclassified")
                    for f in (r["facts"] if r and r["status"] == "found" else [])
                    if f.get("data"))
    out["unreadable_files"] = sum(kinds.values())
    out["unreadable_kinds"] = ";".join(f"{k}={v}" for k, v in sorted(kinds.items()))
    return out


def kind_totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Files that could not be read as rows, by kind, over all datasets."""
    total: Counter[str] = Counter()
    for r in rows:
        for part in filter(None, r["unreadable_kinds"].split(";")):
            kind, n = part.split("=")
            total[kind] += int(n)
    return dict(total)


def main(list_path: Path) -> None:
    frozen = json.loads(list_path.read_text("utf-8"))
    state = State(ROOT / "launch" / "state.sqlite")
    rows = {}
    for d in frozen["datasets"]:
        rows[d["id"]] = {"rank": d["rank"], "id": d["id"], "downloads_30d": d["downloads_30d"],
                         "sha": (d.get("sha") or "")[:12],
                         "bytes_parquet": d.get("bytes_parquet")}
    errors: dict[str, Counter[str]] = {"A": Counter(), "B": Counter()}
    hashes: dict[str, Counter[str]] = {"A": Counter(), "B": Counter()}
    runs: dict[str, dict[str, float]] = {t: {"seconds": 0.0, "http_requests": 0.0} for t in "AB"}
    for tier, fn in (("A", tier_a), ("B", tier_b)):
        for r in state.rows(tier):
            if r["dataset_id"] not in rows:
                continue
            row = rows[r["dataset_id"]]
            row[f"tier_{tier}"] = r["status"]
            row[f"tier_{tier}_seconds"] = r["seconds"]
            row[f"rescanned_{tier}"] = r["config_hash"] != FIRST_SCAN_HASHES[tier]
            hashes[tier][r["config_hash"]] += 1
            runs[tier]["seconds"] += r["seconds"] or 0
            runs[tier]["http_requests"] += r["http_requests"] or 0
            if r["status"] == "done":
                row.update(fn(json.loads(r["report"])))
            else:
                errors[tier][(r["error"] or "").split(":")[0]] += 1
                row[f"tier_{tier}_error"] = (r["error"] or "")[:160]
    state.close()
    # Repos whose dataset-API listing was cut at 100,000 files in the first scan.
    cap_file = OUT / "listing-truncated.json"
    truncated = set(json.loads(cap_file.read_text("utf-8"))["truncated"]) \
        if cap_file.exists() else set()
    for i in truncated:
        if i in rows:
            rows[i]["listing_cut_off_in_first_scan"] = True
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
    rescan_file = OUT / "rescan-set.json"
    rescan = json.loads(rescan_file.read_text("utf-8")) if rescan_file.exists() else {}
    summary = {
        "listed": len(table),
        "first_scan_config_hashes": FIRST_SCAN_HASHES,
        "tier_A": {
            "config_hashes": dict(hashes["A"]), **runs["A"],
            "rescanned": sum(bool(r.get("rescanned_A")) for r in table),
            "rescan_planned": len(rescan.get("A", [])),
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
            "licence_overall_card_present": dict(Counter(
                f"{r['licence_overall']} ({r['licence_overall_sub']})" for r in a
                if r["card_licence"] == "present" and r["licence_overall"])),
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
            "missing_file_results": sum(r["links_missing_file"] for r in a),
            "missing_file_results_by_dataset": {
                r["id"]: r["links_missing_file"] for r in a if r["links_missing_file"]},
            "file_list_incomplete": sum(bool(r["file_list_incomplete"]) for r in a),
        },
        "tier_B": {
            "config_hashes": dict(hashes["B"]), **runs["B"],
            "rescanned": sum(bool(r.get("rescanned_B")) for r in table),
            "rescan_planned": len(rescan.get("B", [])),
            "done": len(b), "failed": sum(r.get("tier_B") == "failed" for r in table),
            "errors": dict(errors["B"]),
            "scan_kind": dict(Counter(r["scan"] for r in b)),
            "scan_source": dict(Counter(r["scan_source"] for r in b)),
            "partial_listing": dict(Counter(r["scan"] for r in b
                                            if not r["listing_complete"])),
            "fetch_git": dict(Counter(r["fetch_git"] for r in b)),
            "fetch_git_files": sum(r["fetch_git_files"] or 0 for r in b),
            "fetch_http_files": sum(r["fetch_http_files"] or 0 for r in b),
            "slowest": [(r["id"], r["tier_B_seconds"]) for r in sorted(
                b, key=lambda r: -(r["tier_B_seconds"] or 0))[:6]],
            "download_capped": sum(bool(r["download_capped"]) for r in b),
            "bytes_read_total": sum(r["bytes_read"] or 0 for r in b),
            "rows_scanned_total": sum(r["rows_scanned"] or 0 for r in b),
            "unreadable_kinds": kind_totals(b),
            **{k: {"found": share(sum(r[k] == "found" for r in scanned),
                                  sum(r[k] in ("found", "none found") for r in scanned)),
                   "statuses": dict(Counter(r[k] for r in b))}
               for k in ("duplicates", "leakage", "empty", "unreadable", "pii")},
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", "utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
