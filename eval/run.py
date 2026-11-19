"""Run the accuracy evaluation (PLAN.md section 8, tasks 4.5-4.6).

Usage (PowerShell, from the ScanCode venv so both scanners run on identical inputs):
    python eval/run.py dev --grid      every threshold in config.yml's grid, dev split
    python eval/run.py test            the frozen thresholds, test split (needs the tag)

For each answer-key row: find the audit-time card revision (eval/revisions.py), then run the
licence check on `hf:<id>@<sha>` once per scanner configuration. All configurations of one row
share one in-memory HTTP memo, so they see exactly the same inputs (the GitHub HEAD read
included); responses pinned to a revision are also cached on disk in eval/cache/http.

Results: eval/results/runs/<split>.jsonl, one line per (row, configuration). Resumable: rows
already written are skipped. Ctrl-C stops after the current row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
import subprocess
import sys
import time
from itertools import product
from pathlib import Path
from typing import Any, ClassVar

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from revisions import RevisionCache

from datasetvet import pipeline
from datasetvet.checks.licence import card_licence, card_where
from datasetvet.config import Settings
from datasetvet.http import FetchError, Http, hf_token_present
from datasetvet.hubs.huggingface import DatasetNotFound, HuggingFaceAdapter
from datasetvet.licences import matcher, spdx
from datasetvet.licences.matcher import Detection
from datasetvet.licences.scanner import (
    BuiltinScanner,
    ScanCodeScanner,
    ScanCodeUnavailable,
    scancode_detections,
)

KEY = ROOT / "eval" / "key" / "key.json"
CONFIG = ROOT / "eval" / "config.yml"
RUNS = ROOT / "eval" / "results" / "runs"
CACHE = ROOT / "eval" / "cache"
TAG = "eval-config-v1"


# -- HTTP memo: identical inputs for every configuration of one row ----------------------------

class MemoHttp(Http):
    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self.memo: dict[tuple, Any] = {}

    def request(self, method: str, url: str, **kw: Any):  # type: ignore[override]
        if method != "GET":
            return super().request(method, url, **kw)
        key = (url, json.dumps(kw.get("params"), sort_keys=True), kw.get("max_bytes"),
               kw.get("auth", True), json.dumps(kw.get("headers"), sort_keys=True))
        if key not in self.memo:
            try:
                self.memo[key] = super().request(method, url, **kw)
            except FetchError as exc:
                self.memo[key] = exc
        hit = self.memo[key]
        if isinstance(hit, FetchError):
            raise hit
        return hit


# -- scanner configurations ---------------------------------------------------------------------

class BuiltinAt(BuiltinScanner):
    def __init__(self, dice: float, contain: float):
        self.dice, self.contain = dice, contain
        self.label = f"builtin dice={dice:.2f} contain={contain:.2f}"

    def describe(self) -> str:
        return (f"built-in matcher (SPDX licence list {spdx.list_version()}; full text dice >= "
                f"{self.dice:.2f}, containment >= {self.contain:.2f}, exact names and URLs)")

    def detect(self, text: str) -> list[Detection]:
        old = matcher.DICE_MIN, matcher.CONTAIN_MIN
        matcher.DICE_MIN, matcher.CONTAIN_MIN = self.dice, self.contain
        try:
            return matcher.detect(text)
        finally:
            matcher.DICE_MIN, matcher.CONTAIN_MIN = old


class ScanCodeAt:
    name = "scancode"
    _base: ScanCodeScanner | None = None
    _raw: ClassVar[dict[str, dict[str, Any]]] = {}

    def __init__(self, min_score: float):
        if ScanCodeAt._base is None:
            ScanCodeAt._base = ScanCodeScanner()
        self.min_score = min_score
        self.label = f"scancode min_score={min_score:g}"

    def describe(self) -> str:
        assert self._base is not None
        return f"ScanCode toolkit {self._base._version} (detections with score >= " \
               f"{self.min_score:g})"

    def detect(self, text: str) -> list[Detection]:
        assert self._base is not None
        k = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
        if k not in self._raw:
            if len(self._raw) > 2000:
                self._raw.clear()
            self._raw[k] = self._base.raw(text)
        return scancode_detections(self._raw[k], self.min_score)


def configurations(cfg: dict[str, Any], grid: bool, which: list[str]) -> list[Any]:
    out: list[Any] = []
    if "builtin" in which:
        if grid:
            g = cfg["grid"]["builtin"]
            out += [BuiltinAt(d, c) for d, c in product(g["dice_min"], g["contain_min"])]
        else:
            f = cfg["frozen"]["builtin"]
            out.append(BuiltinAt(f["dice_min"], f["contain_min"]))
    if "scancode" in which:
        if grid:
            out += [ScanCodeAt(s) for s in cfg["grid"]["scancode"]["min_score"]]
        else:
            out.append(ScanCodeAt(cfg["frozen"]["scancode"]["min_score"]))
    return out


# -- one row --------------------------------------------------------------------------------

def aggregate(c1_state: str, statuses: list[str]) -> str:
    """config.yml `aggregation`, fixed before any run."""
    if c1_state == "missing":
        return "missing"
    if "inconsistent" in statuses:
        return "inconsistent"
    if "consistent" in statuses:
        return "consistent"
    return "unknown"


def q1_match(row: dict[str, Any], c1: dict[str, Any]) -> bool:
    if row["card_kind"] == "missing":
        return c1["state"] == "missing"
    if row["card_kind"] == "spdx" and c1["expression"]:
        return spdx.relation(row["card_spdx"], c1["expression"]).kind == "equivalent"
    return False


def run_row(row: dict[str, Any], rev: dict[str, Any], configs: list[Any], http: MemoHttp,
            settings: Settings) -> list[dict[str, Any]]:
    http.memo.clear()
    base = {"hf_id": row["hf_id"], "split": row["split"], "expected": row["expected"],
            "revision": rev}
    if not rev.get("sha"):
        return [dict(base, config=c.label, scanner=c.name, status=None,
                     excluded="no audit-time revision: " + rev.get("note", "")) for c in configs]
    ref = f"hf:{row['hf_id']}@{rev['sha']}"
    adapter = HuggingFaceAdapter(http)
    try:
        ds = adapter.resolve(ref)
        card = adapter.card(ds)
    except (DatasetNotFound, FetchError, ValueError) as exc:
        return [dict(base, config=c.label, scanner=c.name, status=None,
                     excluded=f"card at the audit-time revision not readable: {exc}"[:300])
                for c in configs]
    where, ev = card_where(card, ds.revision)
    c1o = card_licence(card.metadata, ev, where)
    c1 = {"state": c1o.state, "expression": c1o.expression, "values": c1o.values,
          "reason": c1o.reason}
    out = []
    for conf in configs:
        pipeline.get_scanner = lambda _choice, conf=conf: conf  # type: ignore[assignment]
        t0 = time.monotonic()
        try:
            report = pipeline.run_check(ref, settings, http=http)
        except Exception as exc:  # noqa: BLE001  record and carry on
            out.append(dict(base, config=conf.label, scanner=conf.name, c1=c1,
                            q1_match=q1_match(row, c1), status="unknown",
                            error=f"{type(exc).__name__}: {exc}"[:300]))
            continue
        comps = [{"check": r.check, "status": str(r.status), "sub": r.data.get("sub"),
                  "other": [d["expression"] for d in r.data.get("other", [])]
                  if isinstance(r.data.get("other"), list) else r.data.get("other")}
                 for r in report.results if r.check.startswith("licence.")]
        out.append(dict(base, config=conf.label, scanner=conf.name, c1=c1,
                        q1_match=q1_match(row, c1), comparisons=comps,
                        status=aggregate(c1["state"], [c["status"] for c in comps]),
                        not_checked=[n for n in report.not_checked if "licen" in n][:6],
                        dpi_github_licence=row.get("dpi_github_licence"),
                        seconds=round(time.monotonic() - t0, 2)))
    return out


# -- driver -----------------------------------------------------------------------------------

def check_frozen() -> str:
    tag = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "-q", "--verify",
                          f"refs/tags/{TAG}"], check=False, capture_output=True, text=True)
    if tag.returncode:
        raise SystemExit(f"the test split needs the tag {TAG} (freeze config.yml first)")
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", TAG, "--",
                           "eval/config.yml", "eval/run.py", "src/"], check=False)
    if diff.returncode:
        raise SystemExit(f"eval/config.yml, eval/run.py or src/ differ from {TAG}")
    return tag.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("split", choices=["dev", "test"])
    ap.add_argument("--grid", action="store_true", help="every grid value (dev only)")
    ap.add_argument("--scanners", default="builtin,scancode")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    if args.grid and args.split == "test":
        raise SystemExit("the grid is for the dev split only")
    frozen_at = check_frozen() if args.split == "test" else None
    cfg = yaml.safe_load(CONFIG.read_text("utf-8"))
    try:
        configs = configurations(cfg, args.grid, args.scanners.split(","))
    except ScanCodeUnavailable as exc:
        raise SystemExit(str(exc)) from exc
    rows = [r for r in json.loads(KEY.read_text("utf-8"))["rows"]
            if r["expected"] and r["split"] == args.split]
    if args.limit:
        rows = rows[:args.limit]
    out_path = RUNS / f"{args.split}{'-grid' if args.grid else ''}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in out_path.read_text("utf-8").splitlines():
            r = json.loads(line)
            done.add((r["hf_id"], r["config"]))
    labels = [c.label for c in configs]
    s = cfg["settings"]
    settings = Settings(check_links=s["check_links"], check_data=s["check_data"],
                        provenance_depth=s["provenance_depth"],
                        check_sources=s["check_sources"], cache_dir=CACHE, use_cache=True)
    http = MemoHttp(CACHE, host_interval=1.0)
    revs = RevisionCache(CACHE / "revisions.json")
    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    meta = {"split": args.split, "grid": args.grid, "configs": labels,
            "hf_token": hf_token_present(), "github_token": False,
            "frozen_at": frozen_at, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    print(json.dumps(meta), flush=True)
    todo = [r for r in rows if any((r["hf_id"], lab) not in done for lab in labels)]
    print(f"{len(rows)} rows, {len(todo)} to do, {len(configs)} configuration(s)", flush=True)
    with open(out_path, "a", encoding="utf-8") as fh:
        for i, row in enumerate(todo, 1):
            if stop["now"]:
                print("stopped by Ctrl-C; resume with the same command", flush=True)
                break
            t0 = time.monotonic()
            try:
                rev = revs.get(http, row["hf_id"], row["audit_date"])
            except FetchError as exc:
                rev = {"sha": None, "note": f"commits API fetch failed: {exc}"}
            recs = [r for r in run_row(row, rev, configs, http, settings)
                    if (r["hf_id"], r["config"]) not in done]
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            statuses = ",".join(str(r.get("status")) for r in recs[:2])
            print(f"[{i}/{len(todo)}] {row['hf_id']} expected={row['expected']} "
                  f"ours={statuses} {time.monotonic() - t0:.1f}s calls={http.network_calls}",
                  flush=True)
    http.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
