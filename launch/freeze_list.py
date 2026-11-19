"""Freeze the launch-scan list and measure its budget (PLAN.md section 10, task 4.1).

Usage:  python launch/freeze_list.py [N]      (default 500)

Pages through /api/datasets?sort=downloads&direction=-1 (downloads = the Hub's last-30-days
count) until N datasets that are neither private nor disabled are listed, then reads each
one's size from the Dataset Viewer's /size endpoint (one request per second; the viewer
publishes no rate limits). Writes launch/lists/top<N>-<date>.json. Nothing is downloaded.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from datasetvet.http import FetchError, Http, hf_token_present

HUB = "https://huggingface.co"
VIEWER = "https://datasets-server.huggingface.co"
OUT = ROOT / "launch" / "lists"


def list_top(http: Http, n: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    out: list[dict[str, Any]] = []
    skipped = {"private": 0, "disabled": 0}
    url: str | None = f"{HUB}/api/datasets?sort=downloads&direction=-1&limit=100"
    rank = 0
    while url and len(out) < n:
        resp = http.get(url)
        if not resp.ok:
            raise SystemExit(f"listing failed: HTTP {resp.status}")
        for d in resp.json():
            rank += 1
            if d.get("private"):
                skipped["private"] += 1
                continue
            if d.get("disabled"):
                skipped["disabled"] += 1
                continue
            out.append({"rank": rank, "id": d["id"], "sha": d.get("sha"),
                        "downloads_30d": d.get("downloads"), "gated": d.get("gated", False),
                        "license_tags": [t for t in d.get("tags", [])
                                         if t.startswith("license:")]})
            if len(out) == n:
                break
        link = resp.headers.get("link", "")
        url = link.split(";")[0].strip("<> ") if 'rel="next"' in link else None
    return out, skipped


def size(http: Http, ds_id: str) -> dict[str, Any]:
    try:
        resp = http.get(f"{VIEWER}/size", params={"dataset": ds_id}, timeout=60)
    except FetchError as exc:
        return {"size_error": f"{exc.kind}"}
    if not resp.ok:
        try:
            err = resp.json().get("error", "")[:160]
        except ValueError:
            err = ""
        return {"size_error": f"HTTP {resp.status} {err}".strip()}
    s = (resp.json().get("size") or {}).get("dataset") or {}
    return {"bytes_parquet": s.get("num_bytes_parquet_files"),
            "bytes_original": s.get("num_bytes_original_files"),
            "rows": s.get("num_rows"), "rows_estimated": s.get("estimated_num_rows"),
            "size_partial": bool(resp.json().get("partial"))}


def main(n: int) -> None:
    http = Http(None, host_interval=1.0)
    t0 = time.time()
    rows, skipped = list_top(http, n)
    for i, r in enumerate(rows, 1):
        r.update(size(http, r["id"]))
        if i % 50 == 0:
            print(f"{i}/{len(rows)} sizes read", flush=True)
    day = time.strftime("%Y-%m-%d")
    OUT.mkdir(parents=True, exist_ok=True)
    known = [r["bytes_parquet"] for r in rows if r.get("bytes_parquet")]
    meta = {"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "n": len(rows),
            "skipped_while_listing": skipped, "hf_token": hf_token_present(),
            "requests": http.network_calls, "seconds": round(time.time() - t0),
            "sizes_known": len(known), "bytes_parquet_known_total": sum(known)}
    path = OUT / f"top{n}-{day}.json"
    path.write_text(json.dumps({"meta": meta, "datasets": rows}, indent=1) + "\n", "utf-8")
    print(json.dumps(meta, indent=1))
    print(f"-> {path}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 500)
