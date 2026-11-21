"""Resumable launch scan of the frozen top-500 list (PLAN.md section 10, tasks 4.2 and 4.7).

Usage:
    python launch/run.py LIST --tier A [--max N]     card, licence, provenance, links
    python launch/run.py LIST --tier B [--max N]     data health (no licence or link checks)

- Every dataset is checked at the revision frozen in LIST (`hf:<id>@<sha>`), so a re-run
  checks the same files.
- State: launch/state.sqlite, one row per (dataset, tier). Finished rows whose revision and
  config hash match are skipped, so the same command resumes. `--retry-failed` re-runs rows
  that raised.
- Rate limits: one `datasetvet.http.Http` for the whole run. Its limiter reads the Hub's
  RateLimit headers on every response and pauses below 20% of the window's quota; 429s wait
  for the reset. Non-API hosts get one request per second.
- Batches of `--batch` datasets (default 25) with a checkpoint line after each; `--max N`
  stops after N datasets this invocation. Ctrl-C finishes the dataset in flight and exits.
- Each report is also written to launch/results/reports/<tier>/<org>__<name>.json.
- `--only FILE` restricts a run to the datasets named in FILE (a JSON object `{"A": [...],
  "B": [...]}` as written by launch/rescan_set.py, or one dataset id per line). A rescan under
  a new config hash replaces only those rows; every other row keeps the hash of the run that
  made it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "launch"))

from state import State

STATE = ROOT / "launch" / "state.sqlite"
REPORTS = ROOT / "launch" / "results" / "reports"

# Tier B limits, chosen from the measured budget (task 4.1, launch/lists/top500-2026-11-19.json):
# 138 of the 251 datasets with a known size are <= 100 MB (1.4 GB together), so those get a
# full scan; everything larger is sampled (10,000 rows) and downloads at most 100 MB. A first
# try with 200 MB measured about 4 MB/s on this laptop (download + hashing), i.e. over 4 hours
# for the list, so the limits were halved after 7 datasets.
TIER_B = {"max_scan_bytes": "100MB", "sample_rows": 10_000, "max_download_bytes": "100MB",
          "seed": 0}


def tier_settings(tier: str, cache_dir: Path) -> Any:
    from datasetvet.config import Settings, parse_bytes

    if tier == "A":
        return Settings(check_data=False, check_links=True, check_licences=True,
                        provenance_depth=2, scanner="builtin", cache_dir=cache_dir)
    return Settings(check_data=True, check_links=False, check_licences=False,
                    max_scan_bytes=parse_bytes(TIER_B["max_scan_bytes"]),
                    sample_rows=int(TIER_B["sample_rows"]),
                    max_download_bytes=parse_bytes(TIER_B["max_download_bytes"]),
                    seed=int(TIER_B["seed"]), scanner="builtin", cache_dir=cache_dir)


# The code a launch scan runs: its git tree ids go into the config hash, so a finished row
# names the exact committed code that made it, and any change to that code re-runs the scan.
CODE_PATHS = ("src", "launch/run.py", "launch/state.py", "pyproject.toml")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def code_identity() -> dict[str, Any]:
    """HEAD's commit and the tree ids of CODE_PATHS; refuses uncommitted changes there."""
    dirty = _git("status", "--porcelain", "--", *CODE_PATHS)
    if dirty:
        raise SystemExit("uncommitted changes in the launch scan's code; commit them first so "
                         "the config hash names the code:\n" + dirty)
    return {"commit": _git("rev-parse", "HEAD"),
            "trees": {p: _git("rev-parse", f"HEAD:{p}") for p in CODE_PATHS}}


def config_hash(tier: str, settings: Any, list_name: str,
                code: dict[str, Any] | None = None) -> str:
    from datasetvet import __version__

    blob = json.dumps({"tier": tier, "settings": settings.public(), "list": list_name,
                       "version": __version__, "code": (code or {}).get("trees")},
                      sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def load_only(path: Path, tier: str) -> set[str]:
    """Dataset ids named in a `--only` file: JSON `{"A": [...], "B": [...]}` or one id per line."""
    text = path.read_text("utf-8")
    if path.suffix.lower() == ".json":
        return set(json.loads(text).get(tier, []))
    return {ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")}


def select_only(datasets: list[dict[str, Any]], only: set[str]) -> list[dict[str, Any]]:
    """The listed datasets whose id is in `only`, in list order. A name not in the list is an
    error: a typo must not silently rescan nothing."""
    unknown = only - {d["id"] for d in datasets}
    if unknown:
        raise SystemExit("not in the frozen list: " + ", ".join(sorted(unknown)))
    return [d for d in datasets if d["id"] in only]


def run(datasets: list[dict[str, Any]], tier: str, state: State, chash: str,
        check: Callable[[dict[str, Any]], tuple[str, int]], *, batch: int = 25,
        max_n: int | None = None, retry_failed: bool = False,
        stop: dict[str, bool] | None = None, say: Callable[[str], None] = print) -> int:
    """Check every unfinished dataset; returns how many were checked this call.
    `check(ds)` returns (report JSON, HTTP requests) or raises."""
    stop = stop if stop is not None else {"now": False}
    todo = [d for d in datasets
            if not state.finished(d["id"], tier, d.get("sha"), chash, retry_failed)]
    say(f"tier {tier}: {len(datasets)} listed, {len(datasets) - len(todo)} finished, "
        f"{len(todo)} to do" + (f", this call at most {max_n}" if max_n else ""))
    n = 0
    for i, ds in enumerate(todo, 1):
        if stop["now"] or (max_n is not None and n >= max_n):
            break
        t0 = time.monotonic()
        try:
            report, calls = check(ds)
            state.put(ds["id"], tier, ds.get("sha"), chash, "done", report=report,
                      seconds=round(time.monotonic() - t0, 2), http_requests=calls)
            line = "done"
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001  one dataset failing must not stop the scan
            state.put(ds["id"], tier, ds.get("sha"), chash, "failed",
                      error=f"{type(exc).__name__}: {exc}"[:500],
                      seconds=round(time.monotonic() - t0, 2))
            line = f"failed ({type(exc).__name__})"
        n += 1
        say(f"  [{i}/{len(todo)}] {ds['id']}: {line} in {time.monotonic() - t0:.1f}s")
        if n % batch == 0:
            say(f"checkpoint: {n} checked this call")
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("list", type=Path)
    ap.add_argument("--tier", choices=["A", "B"], required=True)
    ap.add_argument("--max", type=int, default=None, help="stop after N datasets")
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--only", type=Path, default=None, metavar="FILE",
                    help="only the datasets named in FILE (see the module docstring)")
    ap.add_argument("--shard", default=None, metavar="I/N",
                    help="only datasets whose list position %% N == I (parallel workers)")
    args = ap.parse_args(argv)

    from datasetvet.config import default_cache_dir
    from datasetvet.http import Http
    from datasetvet.pipeline import run_check
    from datasetvet.report.json_out import to_json

    frozen = json.loads(args.list.read_text("utf-8"))
    datasets = frozen["datasets"]
    if args.only:
        datasets = select_only(datasets, load_only(args.only, args.tier))
    if args.shard:
        i, n_shards = (int(x) for x in args.shard.split("/"))
        datasets = [d for k, d in enumerate(datasets) if k % n_shards == i]
    settings = tier_settings(args.tier, default_cache_dir())
    code = code_identity()
    chash = config_hash(args.tier, settings, args.list.name, code)
    state = State(STATE)
    http = Http(settings.cache_dir, host_interval=1.0)
    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    out_dir = REPORTS / args.tier
    out_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"tier": args.tier, "config_hash": chash, "commit": code["commit"],
                      "authenticated": http.authenticated, "list": args.list.name}),
          flush=True)

    def check(ds: dict[str, Any]) -> tuple[str, int]:
        before = http.network_calls
        ref = f"hf:{ds['id']}@{ds['sha']}" if ds.get("sha") else f"hf:{ds['id']}"
        report = to_json(run_check(ref, settings, http=http))
        name = ds["id"].replace("/", "__") + ".json"
        (out_dir / name).write_text(report, "utf-8")
        return report, http.network_calls - before

    try:
        n = run(datasets, args.tier, state, chash, check, batch=args.batch, max_n=args.max,
                retry_failed=args.retry_failed, stop=stop,
                say=lambda m: print(m, flush=True))
    finally:
        http.close()
        rows = [r for r in state.rows(args.tier) if r["config_hash"] == chash]
        print(f"tier {args.tier}: {sum(r['status'] == 'done' for r in rows)} done, "
              f"{sum(r['status'] == 'failed' for r in rows)} failed of {len(datasets)} "
              f"listed; {http.network_calls} HTTP requests this call", flush=True)
        state.close()
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
