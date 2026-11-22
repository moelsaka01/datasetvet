"""Phase 5.5, step 2: draw the held-out rows and build the blind labelling sheet (PLAN.md 8.1).

Usage:  python eval/holdout/draw.py            draw 120 rows (seed 20261122), write the sheet
        python eval/holdout/draw.py --batch b  the pre-registered second batch (seed 20261123,
                                               60 rows), only if fewer than 60 rows are scorable

Population: the launch list (launch/lists/top500-2026-11-19.json), each dataset at its frozen
sha. Removed before drawing: every HF repo named in any DPI data summary at the pinned DPI
commit (all of them, not only the key rows), and KakologArchives/KakologArchives (frozen sha
gone). The remaining ids are sorted by lower-cased id and sampled with random.Random(seed).

The sheet shows only what the card itself says (its YAML licence fields copied verbatim and the
URLs written in it), pinned links, and whether the Hub marks the repo gated. It runs no
datasetvet check and shows no datasetvet output. Card copies go to eval/holdout/cards/ (not
committed: third-party text); the sheet records each copy's SHA-256 so it can be verified.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from build_key import DPI_SHA, hf_id_of

LIST = ROOT / "launch" / "lists" / "top500-2026-11-19.json"
DPI = ROOT / "eval" / "cache" / "dpi"
OUT = ROOT / "eval" / "holdout"
GONE = {"kakologarchives/kakologarchives"}
BATCHES = {"a": (20261122, 120, "sheet.csv"), "b": (20261123, 60, "sheet-b.csv")}
MAX_URLS = 25
MAX_CARD_BYTES = 2 * 1024 * 1024
LABEL_COLUMNS = ["expert_licences", "expected_status", "confidence", "notes"]
_URL_RE = re.compile(r"https?://[^\s<>\"'`)\]}|]+", re.IGNORECASE)


def dpi_repos(clone: Path) -> set[str]:
    """Every HF repo named in any DPI data summary at DPI_SHA, lower-cased."""
    import subprocess

    head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    if head != DPI_SHA:
        raise SystemExit(f"{clone} is at {head}, expected {DPI_SHA}")
    out = set()
    for f in sorted((clone / "data_summaries").glob("*.json")):
        for e in json.loads(f.read_text("utf-8")).values():
            hf = hf_id_of(e)
            if hf:
                out.add(hf.lower())
    return out


def population(items: list[dict[str, Any]], dpi: set[str]) -> list[dict[str, Any]]:
    keep = [d for d in items if d["id"].lower() not in dpi and d["id"].lower() not in GONE]
    return sorted(keep, key=lambda d: d["id"].lower())


def draw(pool: list[dict[str, Any]], seed: int, n: int) -> list[dict[str, Any]]:
    return random.Random(seed).sample(pool, n)


def urls_in(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in _URL_RE.finditer(text):
        u = m.group(0).rstrip(".,;:!?*_")
        seen.setdefault(u, None)
    return list(seen)


def verbatim(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def sheet_row(n: int, d: dict[str, Any], adapter: Any, cards_dir: Path) -> dict[str, Any]:
    from datasetvet.http import FetchError
    from datasetvet.hubs.huggingface import DatasetNotFound, parse_card
    from datasetvet.model import Evidence

    ds_id, sha = d["id"], d["sha"]
    row: dict[str, Any] = {
        "row": n, "hf_id": ds_id, "frozen_sha": sha, "gated": "yes" if d.get("gated") else "no",
        "card_url": f"https://huggingface.co/datasets/{ds_id}/blob/{sha}/README.md",
        "files_url": f"https://huggingface.co/datasets/{ds_id}/tree/{sha}",
        "card_sha256": "", "card_note": "",
        "yaml_license": "", "yaml_license_name": "", "yaml_license_link": "",
        "urls_in_card_count": 0, "urls_in_card": "",
    }
    try:
        ds = adapter.resolve(f"hf:{ds_id}@{sha}")
    except (DatasetNotFound, FetchError, ValueError) as exc:
        row["card_note"] = f"card not readable at the frozen sha: {exc}"[:200]
        return row
    # The README is fetched directly at the sha (no file listing: a repo with more than
    # 100,000 files would be paged in full just to find it). YAML parsed as datasetvet does.
    text: str | None = None
    why = ""
    try:
        text = adapter.read_text(ds, "README.md", MAX_CARD_BYTES).text
    except FetchError as exc:
        why = str(exc)
    if text is not None:
        md = parse_card(text, Evidence(url=adapter.blob_url(ds, "README.md"))).metadata or {}
    else:
        md = adapter.info(ds).get("cardData") or {}
    row["yaml_license"] = verbatim(md.get("license"))
    row["yaml_license_name"] = verbatim(md.get("license_name"))
    row["yaml_license_link"] = verbatim(md.get("license_link"))
    if text is None and "HTTP 404" in why:
        row["card_note"] = "no README.md at the frozen sha (HTTP 404), so the card has no YAML"
        urls = []
    elif text is None:
        row["card_note"] = ("README text not readable anonymously"
                            + (" (gated)" if d.get("gated") else "")
                            + (f": {why}" if why else "")
                            + "; YAML fields from the Hub API")[:200]
        urls = urls_in(json.dumps(md, ensure_ascii=False))
    else:
        card_text = text
        raw = card_text.encode("utf-8")
        row["card_sha256"] = hashlib.sha256(raw).hexdigest()
        (cards_dir / (ds_id.replace("/", "__") + ".md")).write_bytes(raw)
        urls = urls_in(card_text)
    row["urls_in_card_count"] = len(urls)
    row["urls_in_card"] = " | ".join(urls[:MAX_URLS]) + (" | ..." if len(urls) > MAX_URLS
                                                         else "")
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", choices=sorted(BATCHES), default="a")
    args = ap.parse_args(argv)
    seed, n, name = BATCHES[args.batch]
    items = json.loads(LIST.read_text("utf-8"))["datasets"]
    dpi = dpi_repos(DPI)
    pool = population(items, dpi)
    if args.batch == "b":
        with open(OUT / "sheet.csv", encoding="utf-8") as fh:
            first = {r["hf_id"].lower() for r in csv.DictReader(fh)}
        pool = [d for d in pool if d["id"].lower() not in first]
    picked = draw(pool, seed, n)
    print(f"launch list {len(items)}; in DPI {sum(d['id'].lower() in dpi for d in items)}; "
          f"pool {len(pool)}; drawn {len(picked)} (seed {seed})", flush=True)

    from datasetvet.http import Http
    from datasetvet.hubs.huggingface import HuggingFaceAdapter

    cards_dir = OUT / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    http = Http(ROOT / "eval" / "cache", host_interval=1.0)
    adapter = HuggingFaceAdapter(http)
    rows = []
    for i, d in enumerate(picked, 1):
        rows.append(sheet_row(i, d, adapter, cards_dir))
        print(f"[{i}/{len(picked)}] {d['id']}", flush=True)
    http.close()
    cols = list(rows[0]) + LABEL_COLUMNS
    with open(OUT / name, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(dict(r, **{c: "" for c in LABEL_COLUMNS}))
    (OUT / f"draw-{args.batch}.json").write_text(json.dumps({
        "list": LIST.relative_to(ROOT).as_posix(), "dpi_sha": DPI_SHA,
        "launch_list_size": len(items), "removed_dpi": sum(d["id"].lower() in dpi
                                                           for d in items),
        "removed_gone": sorted(GONE), "pool": len(pool), "seed": seed, "drawn": n,
        "ids": [d["id"] for d in picked]}, indent=1) + "\n", "utf-8")
    print(f"wrote {OUT / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
