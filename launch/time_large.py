"""Time datasetvet on one very large Hugging Face repo (Phase 4.5, RESULTS.md section 4).

Usage:
    python launch/time_large.py ID SHA listing            list the repo's files, cold cache
    python launch/time_large.py ID SHA read-launch        data health with the launch (Tier B) limits
    python launch/time_large.py ID SHA read-default       data health with datasetvet's defaults
    python launch/time_large.py ID SHA all [--cap MIN]    the three above, each in its own process

Each phase is a separate process with its own cache directory, so no phase gets files another
one downloaded. `all` runs `listing` first and gives each read phase a copy of the listing's
cache (the file list is not fetched again), so a read phase measures the read alone; listing
time plus read time is what a user waits. A read phase is stopped after --cap minutes (default
20): its progress lines carry a time stamp, so the file count reached by then can be read off.

Writes launch/results/timing-<org>__<name>.json (one entry per phase) and keeps the phase logs
in launch/results/tmp/. Uses the Hugging Face token if one is present (the owner allowed that
for this measurement); the result records whether it did.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "launch"))
TMP = ROOT / "launch" / "results" / "tmp"


def phase_listing(ds_id: str, sha: str, cache: Path) -> dict:
    from datasetvet.http import Http
    from datasetvet.hubs.huggingface import HuggingFaceAdapter, file_format, is_non_data_path

    http = Http(cache, host_interval=1.0)
    try:
        hf = HuggingFaceAdapter(http)
        ds = hf.resolve(f"hf:{ds_id}@{sha}")
        t0 = time.monotonic()
        listing = hf.listing(ds)
        seconds = time.monotonic() - t0
        paths = [f.path for f in listing.files]
        data = [p for p in paths if file_format(p) and not is_non_data_path(p)
                and p != "README.md" and not any(x.startswith(".") for x in p.split("/"))]
        return {"phase": "listing", "seconds": round(seconds, 1), "files": len(paths),
                "data_files": len(data), "complete": listing.complete, "note": listing.note,
                "http_requests": http.network_calls, "authenticated": http.authenticated}
    finally:
        http.close()


def phase_read(ds_id: str, sha: str, cache: Path, which: str) -> dict:
    from run import TIER_B

    from datasetvet.config import Settings, parse_bytes
    from datasetvet.http import Http
    from datasetvet.pipeline import run_check

    if which == "launch":
        settings = Settings(check_data=True, check_links=False, check_licences=False,
                            max_scan_bytes=parse_bytes(TIER_B["max_scan_bytes"]),
                            sample_rows=int(str(TIER_B["sample_rows"])),
                            max_download_bytes=parse_bytes(TIER_B["max_download_bytes"]),
                            seed=int(str(TIER_B["seed"])), scanner="builtin", cache_dir=cache)
    else:  # datasetvet's own defaults, data health only
        settings = Settings(check_data=True, check_links=False, check_licences=False,
                            scanner="builtin", cache_dir=cache)
    http = Http(cache, host_interval=1.0)
    t0 = time.monotonic()

    def say(msg: str) -> None:
        print(f"[{time.monotonic() - t0:8.1f}s] {msg}", flush=True)

    try:
        report = run_check(f"hf:{ds_id}@{sha}", settings, http=http, progress=say)
        scan = report.scan
        return {"phase": f"read-{which}", "seconds": round(time.monotonic() - t0, 1),
                "finished": True, "scan_kind": getattr(scan, "kind", None),
                "source": getattr(scan, "source", None),
                "rows_scanned": getattr(scan, "rows_scanned", None),
                "bytes_read": getattr(scan, "bytes_read", None),
                "partial": getattr(scan, "partial", None),
                "listing_complete": getattr(scan, "listing_complete", None),
                "http_requests": http.network_calls, "authenticated": http.authenticated,
                "data_fetch": report.settings.get("data_fetch")}
    finally:
        http.close()


def child(ds_id: str, sha: str, phase: str, cache: Path, cap_min: float, log: Path) -> dict:
    """Run one phase in its own process; stop it at `cap_min` minutes (reads only)."""
    out = log.with_suffix(".json")
    out.unlink(missing_ok=True)
    cmd = [sys.executable, "-I", str(Path(__file__).resolve()), ds_id, sha, phase,
           "--cache", str(cache), "--out", str(out)]
    t0 = time.monotonic()
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT)
        try:
            proc.wait(timeout=cap_min * 60 if phase.startswith("read") else None)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, check=False)
            proc.wait()
            elapsed = time.monotonic() - t0
            last = [ln for ln in log.read_text("utf-8", "replace").splitlines() if ln.strip()]
            return {"phase": phase, "finished": False, "stopped_at_seconds": round(elapsed),
                    "cap_minutes": cap_min, "last_progress_lines": last[-6:]}
    if out.exists():
        return json.loads(out.read_text("utf-8"))
    return {"phase": phase, "finished": False, "error": "no result file; see " + str(log)}


def main(argv: list[str]) -> int:
    ds_id, sha, phase = argv[0], argv[1], argv[2]
    opt = {k: argv[i + 1] for i, k in enumerate(argv) if k.startswith("--") and i + 1 < len(argv)}
    if phase == "all":
        cap = float(opt.get("--cap", 20))
        TMP.mkdir(parents=True, exist_ok=True)
        slug = ds_id.replace("/", "__")
        base = TMP / f"timing-{slug}"
        shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True)
        results = [child(ds_id, sha, "listing", base / "cache-listing", cap, base / "listing.log")]
        for which in ("read-launch", "read-default"):
            cache = base / f"cache-{which}"
            shutil.copytree(base / "cache-listing", cache)
            results.append(child(ds_id, sha, which, cache, cap, base / f"{which}.log"))
        out = ROOT / "launch" / "results" / f"timing-{slug}.json"
        out.write_text(json.dumps({"dataset": ds_id, "sha": sha, "cap_minutes": cap,
                                   "phases": results}, indent=1) + "\n", "utf-8")
        print(json.dumps(results, indent=1))
        return 0
    cache = Path(opt["--cache"]) if "--cache" in opt else TMP / "timing-cache"
    cache.mkdir(parents=True, exist_ok=True)
    if phase == "listing":
        res = phase_listing(ds_id, sha, cache)
    else:
        res = phase_read(ds_id, sha, cache, phase.removeprefix("read-"))
    print(json.dumps(res))
    if "--out" in opt:
        Path(opt["--out"]).write_text(json.dumps(res) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    if re.search(r"\bhelp\b|-h\b", " ".join(sys.argv[1:2])) or len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
