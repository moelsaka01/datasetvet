"""Fetch-route equivalence test: the git-pack and parallel download routes must give the same
report as the old one-file-at-a-time route.

Usage:
    python launch/fetch_equivalence.py LIST [--n 40] [--slowest 12] [--route new|http]

Baseline: the Tier B reports already in launch/state.sqlite under `--baseline-hash`. Those
were made by the one-file-at-a-time route at the revision frozen in LIST, and every check is
pinned to that revision, so the same data gives the same report.
- `--route new` (default): git pack + parallel downloads, the new default settings.
- `--route http`: git off and one download at a time, i.e. the old route run again today.
  This checks that the baseline itself is reproducible.

Selected datasets: the `--slowest` slowest baseline rows (where the new route matters) plus
a seeded random sample of the rest, up to `--n`. Each report is compared field by field with
its baseline after removing what is expected to differ: timings (`scan.seconds`,
`created_at`, `fetched_at`), the HTTP request count, the new fetch settings and the fetch
route note. Anything else that differs is a failure (exit 1). Results go to
launch/results/fetch-equivalence-<route>.json.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "launch"))

from state import State

STATE = ROOT / "launch" / "state.sqlite"
OUT = ROOT / "launch" / "results"
BASELINE_HASH = "d1d12f8a1d35321e"  # Tier B, one file at a time, 2026-11-19

DROP_TOP = ("created_at",)
DROP_SETTINGS = ("http_requests", "git_fetch", "fetch_workers", "data_fetch")
TMP_RE = re.compile(r"datasetvet-[A-Za-z0-9_]+")


def normalize(report: dict[str, Any]) -> dict[str, Any]:
    r = copy.deepcopy(report)
    for k in DROP_TOP:
        r.pop(k, None)
    if isinstance(r.get("scan"), dict):
        r["scan"].pop("seconds", None)
    for k in DROP_SETTINGS:
        (r.get("settings") or {}).pop(k, None)

    def walk(o: Any) -> Any:
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items() if k != "fetched_at"}
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, str):
            return TMP_RE.sub("datasetvet-TMP", o)
        return o

    return walk(r)


def diff(a: Any, b: Any, path: str = "", out: list[str] | None = None) -> list[str]:
    out = [] if out is None else out
    if len(out) >= 20:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'new' if k in b else 'baseline'}")
            else:
                diff(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} items in baseline, {len(b)} in new")
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"{path}: baseline {str(a)[:120]!r} != new {str(b)[:120]!r}")
    return out


def select(rows: list[dict[str, Any]], n: int, slowest: int, seed: int) -> list[dict[str, Any]]:
    by_time = sorted(rows, key=lambda r: -(r["seconds"] or 0))
    picked = by_time[:slowest]
    rest = [r for r in rows if r not in picked]
    picked += random.Random(seed).sample(rest, min(len(rest), max(0, n - len(picked))))
    return picked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("list", type=Path)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--slowest", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--route", choices=["new", "http"], default="new")
    ap.add_argument("--baseline-hash", default=BASELINE_HASH)
    ap.add_argument("--ids", nargs="*", help="only these dataset ids (overrides selection)")
    args = ap.parse_args(argv)

    from run import tier_settings

    from datasetvet.config import default_cache_dir
    from datasetvet.http import Http
    from datasetvet.pipeline import run_check
    from datasetvet.report.json_out import to_json

    shas = {d["id"]: d.get("sha") for d in json.loads(args.list.read_text("utf-8"))["datasets"]}
    state = State(STATE)
    rows = [r for r in state.rows("B") if r["status"] == "done"
            and r["config_hash"] == args.baseline_hash and r["sha"] == shas.get(r["dataset_id"])]
    state.close()
    if args.ids:
        rows = [r for r in rows if r["dataset_id"] in set(args.ids)]
    else:
        rows = select(rows, args.n, args.slowest, args.seed)
    settings = tier_settings("B", default_cache_dir())
    if args.route == "http":
        settings = dataclasses.replace(settings, git_fetch=False, fetch_workers=1)
    http = Http(settings.cache_dir, host_interval=1.0)
    print(f"route {args.route}: {len(rows)} datasets, git_fetch={settings.git_fetch}, "
          f"fetch_workers={settings.fetch_workers}, authenticated={http.authenticated}",
          flush=True)

    results = []
    try:
        for i, row in enumerate(rows, 1):
            base = json.loads(row["report"])
            before = http.network_calls
            t0 = time.monotonic()
            try:
                new = json.loads(to_json(run_check(f"hf:{row['dataset_id']}@{row['sha']}",
                                                   settings, http=http)))
                error = None
            except Exception as exc:  # noqa: BLE001  a crash is a failure, keep going
                new, error = None, f"{type(exc).__name__}: {exc}"[:300]
            secs = round(time.monotonic() - t0, 2)
            diffs = ([f"error: {error}"] if error else
                     diff(normalize(base), normalize(new or {})))
            scan = base.get("scan") or {}
            results.append({
                "id": row["dataset_id"], "sha": row["sha"], "equal": not diffs, "diffs": diffs,
                "kind": scan.get("kind"), "source": scan.get("source"),
                "baseline_seconds": row["seconds"], "seconds": secs,
                "baseline_requests": row["http_requests"],
                "requests": http.network_calls - before,
                "data_fetch": ((new or {}).get("settings") or {}).get("data_fetch"),
            })
            print(f"[{i}/{len(rows)}] {'SAME' if not diffs else 'DIFF'} {row['dataset_id']}: "
                  f"{row['seconds']:.0f}s -> {secs:.0f}s, {row['http_requests']} -> "
                  f"{http.network_calls - before} requests", flush=True)
            for d in diffs[:5]:
                print(f"    {d}", flush=True)
    finally:
        http.close()

    same = sum(r["equal"] for r in results)
    summary = {
        "route": args.route, "baseline_hash": args.baseline_hash, "n": len(results),
        "same": same, "different": len(results) - same,
        "baseline_seconds": round(sum(r["baseline_seconds"] or 0 for r in results), 1),
        "seconds": round(sum(r["seconds"] for r in results), 1),
        "baseline_requests": sum(r["baseline_requests"] or 0 for r in results),
        "requests": sum(r["requests"] for r in results),
        "kinds": {k: sum(r["kind"] == k for r in results)
                  for k in sorted({str(r["kind"]) for r in results})},
        "sources": {k: sum(str(r["source"]) == k for r in results)
                    for k in sorted({str(r["source"]) for r in results})},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"fetch-equivalence-{args.route}.json"
    out.write_text(json.dumps({"summary": summary, "rows": results}, indent=1), "utf-8")
    print(json.dumps(summary, indent=1))
    print(f"-> {out}")
    return 0 if same == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
