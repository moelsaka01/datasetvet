"""Phase 5.5 evaluation runner for datasetvet v2 (PLAN.md 8.1).

Usage (from the project venv; the built-in matcher, the plain install):
    python eval/run_v2.py rulework     dev split + the 48 disagreement-sample datasets, every
                                       rule variant (ablation); no tag needed
    python eval/run_v2.py test         the old test split, frozen v2 (needs eval-config-v2);
                                       reported as "no longer blind"

The dataset status is the report's own `licence.summary` result (v2's dataset-level rule), not
an eval-side aggregation. Variants switch the Phase 5.5 rules (module constants in
checks/licence.py) the way eval/run.py switched the matcher thresholds. All variants of one
row share one HTTP memo, so they read identical bytes (GitHub HEAD included).

Results: eval/results/runs/<mode>-v2.jsonl, one line per (row, variant). Resumable.
"""

from __future__ import annotations

import argparse
import csv
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Self

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from evalmods import load
from revisions import RevisionCache

from datasetvet import pipeline
from datasetvet.checks import licence as lic
from datasetvet.checks.licence import card_licence, card_where
from datasetvet.config import Settings
from datasetvet.http import FetchError, hf_token_present
from datasetvet.hubs.huggingface import DatasetNotFound, HuggingFaceAdapter

v1 = load("eval_run_v1", "eval/run.py")  # MemoHttp, BuiltinAt, q1_match

CONFIG = ROOT / "eval" / "config-v2.yml"
RUNS = ROOT / "eval" / "results" / "runs"
TAG = "eval-config-v2"
FROZEN_PATHS = ["eval/config-v2.yml", "eval/run_v2.py", "eval/run.py", "eval/holdout/",
                "src/"]
# the owner fills the label columns in after the freeze; everything else must match the tag
LABEL_FILES = ["eval/holdout/sheet.csv", "eval/holdout/sheet-b.csv"]
RULES = ("CODE_LICENCE_RULE", "SOFTWARE_ASIDE_RULE", "UNCONTRADICTED_RULE",
         "CODE_RULE_NEEDS_DATA_CARD")


class Variant:
    """One setting of the Phase 5.5 rules."""

    def __init__(self, label: str, **rules: bool):
        self.label = label
        self.rules = {k: rules.get(k, False) for k in RULES}

    def __enter__(self) -> Self:
        self._old = {k: getattr(lic, k) for k in RULES}
        for k, v in self.rules.items():
            setattr(lic, k, v)
        return self

    def __exit__(self, *_a: object) -> None:
        for k, v in self._old.items():
            setattr(lic, k, v)


def variants(cfg: dict[str, Any], mode: str) -> list[Variant]:
    if mode == "rulework":
        return [Variant(v["label"], **v.get("rules", {})) for v in cfg["rulework_variants"]]
    f = cfg["frozen"]
    return [Variant("v2", **f["rules"])]


def rulework_rows(key: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dev rows plus the datasets of the two Phase 4 disagreement samples (test rows)."""
    audited: set[str] = set()
    for name in ("builtin", "scancode"):
        with open(ROOT / "eval" / "results" / f"disagreements-{name}.csv",
                  encoding="utf-8") as fh:
            audited |= {r["hf_id"] for r in csv.DictReader(fh)}
    return [dict(r, group="dev" if r["split"] == "dev" else "audited") for r in key
            if r["expected"] and (r["split"] == "dev" or r["hf_id"] in audited)]


def run_row(row: dict[str, Any], rev: dict[str, Any], vs: list[Variant], scanner: Any,
            http: v1.MemoHttp, settings: Settings) -> list[dict[str, Any]]:
    http.memo.clear()
    base = {"hf_id": row["hf_id"], "split": row["split"], "group": row.get("group"),
            "expected": row["expected"], "revision": rev}
    if not rev.get("sha"):
        return [dict(base, config=v.label, status=None,
                     excluded="no audit-time revision: " + rev.get("note", "")) for v in vs]
    ref = f"hf:{row['hf_id']}@{rev['sha']}"
    try:
        adapter = HuggingFaceAdapter(http)
        ds = adapter.resolve(ref)
        card = adapter.card(ds)
    except (DatasetNotFound, FetchError, ValueError) as exc:
        return [dict(base, config=v.label, status=None,
                     excluded=f"card at the audit-time revision not readable: {exc}"[:300])
                for v in vs]
    where, ev = card_where(card, ds.revision)
    c1o = card_licence(card.metadata, ev, where)
    c1 = {"state": c1o.state, "expression": c1o.expression, "values": c1o.values,
          "reason": c1o.reason}
    pipeline.get_scanner = lambda _choice: scanner  # type: ignore[assignment]
    out = []
    for v in vs:
        t0 = time.monotonic()
        with v:
            try:
                report = pipeline.run_check(ref, settings, http=http)
            except Exception as exc:  # noqa: BLE001  record and carry on (counts as unknown)
                out.append(dict(base, config=v.label, c1=c1, status="unknown",
                                error=f"{type(exc).__name__}: {exc}"[:300]))
                continue
        summ = next((r for r in report.results if r.check == "licence.summary"), None)
        comps = [{"check": r.check, "status": str(r.status), "sub": r.data.get("sub"),
                  "other": [d["expression"] for d in r.data.get("other", [])]
                  if isinstance(r.data.get("other"), list) else r.data.get("other")}
                 for r in report.results
                 if r.check.startswith("licence.") and r.check != "licence.summary"]
        out.append(dict(base, config=v.label, c1=c1, q1_match=v1.q1_match(row, c1),
                        comparisons=comps,
                        status=str(summ.status) if summ else "unknown",
                        summary_sub=summ.data.get("sub") if summ else None,
                        dpi_github_licence=row.get("dpi_github_licence"),
                        seconds=round(time.monotonic() - t0, 2)))
    return out


def check_frozen() -> str:
    tag = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "-q", "--verify",
                          f"refs/tags/{TAG}"], check=False, capture_output=True, text=True)
    if tag.returncode:
        raise SystemExit(f"this run needs the tag {TAG} (freeze first)")
    paths = [*FROZEN_PATHS, *(f":(exclude){p}" for p in LABEL_FILES)]
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", TAG, "--", *paths],
                          check=False)
    if diff.returncode:
        raise SystemExit(f"{', '.join(FROZEN_PATHS)} differ from {TAG}")
    status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain",
                             "--untracked-files=all", "--", *paths], capture_output=True,
                            text=True, check=False)
    if status.stdout.strip():
        raise SystemExit("files under the frozen paths are not in the tag: "
                         + "; ".join(status.stdout.splitlines()[:3]))
    return tag.stdout.strip()


def settings_from(cfg: dict[str, Any]) -> Settings:
    s = cfg["settings"]
    return Settings(check_links=s["check_links"], check_data=s["check_data"],
                    provenance_depth=s["provenance_depth"], check_sources=s["check_sources"],
                    cache_dir=v1.CACHE, use_cache=True)


def builtin_scanner(cfg: dict[str, Any]) -> v1.BuiltinAt:
    b = cfg["scanner"]["builtin"]
    return v1.BuiltinAt(b["dice_min"], b["contain_min"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["rulework", "test"])
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    frozen_at = check_frozen() if args.mode == "test" else None
    cfg = yaml.safe_load(CONFIG.read_text("utf-8"))
    vs = variants(cfg, args.mode)
    key = json.loads(v1.KEY.read_text("utf-8"))["rows"]
    rows = (rulework_rows(key) if args.mode == "rulework" else
            [dict(r, group="test") for r in key if r["expected"] and r["split"] == "test"])
    if args.limit:
        rows = rows[:args.limit]
    out_path = RUNS / f"{args.mode}-v2.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in out_path.read_text("utf-8").splitlines():
            r = json.loads(line)
            done.add((r["hf_id"], r["config"]))
    settings = settings_from(cfg)
    scanner = builtin_scanner(cfg)
    http = v1.MemoHttp(v1.CACHE, host_interval=1.0)
    revs = RevisionCache(v1.CACHE / "revisions.json")
    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    print(json.dumps({"mode": args.mode, "variants": [v.label for v in vs],
                      "scanner": scanner.label, "hf_token": hf_token_present(),
                      "github_token": False, "frozen_at": frozen_at,
                      "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}), flush=True)
    todo = [r for r in rows if any((r["hf_id"], v.label) not in done for v in vs)]
    print(f"{len(rows)} rows, {len(todo)} to do, {len(vs)} variant(s)", flush=True)
    with open(out_path, "a", encoding="utf-8") as fh:
        for i, row in enumerate(todo, 1):
            if stop["now"]:
                print("stopped by Ctrl-C; resume with the same command", flush=True)
                break
            try:
                rev = revs.get(http, row["hf_id"], row["audit_date"])
            except FetchError as exc:
                rev = {"sha": None, "note": f"commits API fetch failed: {exc}"}
            recs = [r for r in run_row(row, rev, vs, scanner, http, settings)
                    if (r["hf_id"], r["config"]) not in done]
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{i}/{len(todo)}] {row['hf_id']} expected={row['expected']} "
                  f"v2={recs[-1].get('status') if recs else '-'}", flush=True)
    http.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
