"""Phase 5: confirm the ScanCode threshold on the test split (50 against 90).

The frozen test run (eval-config-v1) scored ScanCode at 50 only. Whether 50 should become the
code default needs 90 scored on the same split. This runs both thresholds in one process, so
they read identical bytes (GitHub included), and writes eval/results/runs/test-threshold.jsonl.

It is a second look at the test split and is labelled as one in RESULTS.md. It does not
replace the frozen test results (eval/results/runs/test.jsonl is not touched) and it does not
use the eval-config-v1 guard, because src/ has moved on since the tag (licence code did not;
the data-health and listing code did).

Usage (PowerShell, from the ScanCode venv):
    python eval/threshold_check.py            run, resumable
    python eval/metrics.py test-threshold     metrics for both thresholds
"""

from __future__ import annotations

import json
import signal
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

import run as ev  # eval/run.py
from revisions import RevisionCache

from datasetvet.config import Settings
from datasetvet.http import FetchError, hf_token_present

THRESHOLDS = (50, 90)
OUT = ROOT / "eval" / "results" / "runs" / "test-threshold.jsonl"


def main() -> int:
    cfg = yaml.safe_load(ev.CONFIG.read_text("utf-8"))
    configs = [ev.ScanCodeAt(s) for s in THRESHOLDS]
    rows = [r for r in json.loads(ev.KEY.read_text("utf-8"))["rows"]
            if r["expected"] and r["split"] == "test"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUT.exists():
        for line in OUT.read_text("utf-8").splitlines():
            r = json.loads(line)
            done.add((r["hf_id"], r["config"]))
    labels = [c.label for c in configs]
    s = cfg["settings"]
    settings = Settings(check_links=s["check_links"], check_data=s["check_data"],
                        provenance_depth=s["provenance_depth"],
                        check_sources=s["check_sources"], cache_dir=ev.CACHE, use_cache=True)
    http = ev.MemoHttp(ev.CACHE, host_interval=1.0)
    revs = RevisionCache(ev.CACHE / "revisions.json")
    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    print(json.dumps({"run": "test-threshold", "configs": labels,
                      "hf_token": hf_token_present(), "github_token": False,
                      "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}), flush=True)
    todo = [r for r in rows if any((r["hf_id"], lab) not in done for lab in labels)]
    print(f"{len(rows)} rows, {len(todo)} to do", flush=True)
    with open(OUT, "a", encoding="utf-8") as fh:
        for i, row in enumerate(todo, 1):
            if stop["now"]:
                print("stopped by Ctrl-C; resume with the same command", flush=True)
                break
            try:
                rev = revs.get(http, row["hf_id"], row["audit_date"])
            except FetchError as exc:
                rev = {"sha": None, "note": f"commits API fetch failed: {exc}"}
            for r in ev.run_row(row, rev, configs, http, settings):
                if (r["hf_id"], r["config"]) not in done:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{i}/{len(todo)}] {row['hf_id']}", flush=True)
    http.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
