"""Phase 5.5, step 4: predictions of A, B and C on the held-out rows (PLAN.md 8.1).

Usage (PowerShell, from the ScanCode venv, so B can run; Git Bash's libmagic crashes ScanCode):
    python eval/holdout/predict.py          needs the tag eval-config-v2 and a fully labelled sheet

Runs only after labelling, so no prediction exists while the owner labels. It reads the label
columns only to check that none is empty, and that the other columns are those of `holdout-v1`.

- A, the HF `license:` tag alone: the Hub's tags at the frozen sha (from the launch list). No tag
  or only `unknown` -> missing; any other tag -> consistent.
- B, ScanCode alone (score >= 50): the dataset repo's README without its YAML front matter, and
  its licence files, at the frozen sha; no stated sources. Tag missing -> missing; no detection
  -> unknown; detected keys == the tag's keys -> consistent; otherwise inconsistent.
- C, datasetvet v2: the report's licence.summary at the frozen sha, built-in matcher, frozen
  rules (eval/config-v2.yml).

All three read one row through one HTTP memo. Output: eval/results/holdout/predictions.jsonl.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from evalmods import load

from datasetvet import pipeline
from datasetvet.checks.licence import LICENCE_FILE_RE, MAX_LICENCE_BYTES, MAX_LICENCE_FILES
from datasetvet.http import FetchError, hf_token_present
from datasetvet.hubs.huggingface import DatasetNotFound, HuggingFaceAdapter
from datasetvet.licences import spdx
from datasetvet.licences.hf_ids import lookup

v1 = load("eval_run_v1", "eval/run.py")
v2 = load("eval_run_v2", "eval/run_v2.py")

HOLDOUT = ROOT / "eval" / "holdout"
OUT = ROOT / "eval" / "results" / "holdout"
LIST = ROOT / "launch" / "lists" / "top500-2026-11-19.json"
SHEETS = [("holdout-v1", "sheet.csv"), ("holdout-v1b", "sheet-b.csv")]
LABELS = ["expert_licences", "expected_status", "confidence", "notes"]
SCORED = {"consistent", "inconsistent", "missing"}
SCANCODE_MIN = 50


# -- the sheet --------------------------------------------------------------------------------

def read_sheet(text: str) -> list[dict[str, str]]:
    """Rows of a sheet; a UTF-8 BOM (Excel adds one when it saves CSV) is ignored."""
    return list(csv.DictReader(io.StringIO(text.removeprefix("﻿"))))


def tagged_sheet(tag: str, name: str) -> str | None:
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{tag}:eval/holdout/{name}"],
                       capture_output=True, text=True, encoding="utf-8", check=False)
    return r.stdout if r.returncode == 0 else None


def check_sheet(rows: list[dict[str, str]], tagged: list[dict[str, str]]) -> list[str]:
    """Problems: label columns empty, or other columns changed since the sheet's tag."""
    out = []
    if [{k: v for k, v in r.items() if k not in LABELS} for r in rows] != \
            [{k: v for k, v in r.items() if k not in LABELS} for r in tagged]:
        out.append("columns other than the labels differ from the tagged sheet")
    for r in rows:
        st = (r.get("expected_status") or "").strip()
        if not st:
            out.append(f"row {r['row']} ({r['hf_id']}): expected_status is empty")
        elif st not in SCORED and not st.startswith("excluded"):
            out.append(f"row {r['row']} ({r['hf_id']}): unknown expected_status {st!r}")
    return out


def labelled_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for tag, name in SHEETS:
        path = HOLDOUT / name
        if not path.exists():
            continue
        tagged = tagged_sheet(tag, name)
        if tagged is None:
            raise SystemExit(f"{name} exists but the tag {tag} does not")
        mine = read_sheet(path.read_text("utf-8"))
        problems = check_sheet(mine, read_sheet(tagged))
        if problems:
            raise SystemExit(f"{name}: " + "; ".join(problems[:5]))
        rows += [dict(r, batch=tag) for r in mine]
    if not rows:
        raise SystemExit("no labelled sheet")
    return rows


# -- A and B ----------------------------------------------------------------------------------

def tag_values(tags: list[str]) -> list[str]:
    return [t.split(":", 1)[1] for t in tags if t.startswith("license:")]


def baseline_a(tags: list[str]) -> str:
    vals = [v for v in tag_values(tags) if v.lower() != "unknown"]
    return "consistent" if vals else "missing"


def tag_keys(tags: list[str]) -> set[str]:
    keys: set[str] = set()
    for v in tag_values(tags):
        if v.lower() == "unknown":
            continue
        h = lookup(v)
        k = h.expression_key
        keys |= spdx.keys(k) if k else {f"LicenseRef-unmapped-{v}"}
    return keys


def baseline_b(tags: list[str], detected: list[str]) -> str:
    if baseline_a(tags) == "missing":
        return "missing"
    keys: set[str] = set()
    for e in detected:
        keys |= spdx.keys(e) or {e}
    if not keys:
        return "unknown"
    return "consistent" if keys == tag_keys(tags) else "inconsistent"


def scancode_texts(adapter: HuggingFaceAdapter, ds: Any, card: Any) -> list[tuple[str, str]]:
    texts = [("README.md (YAML removed)", card.body or "")] if card.text is not None else []
    listing = adapter.listing(ds)
    for path in sorted(f.path for f in listing.files if LICENCE_FILE_RE.search(f.path))[
            :MAX_LICENCE_FILES]:
        try:
            texts.append((path, adapter.read_text(ds, path, MAX_LICENCE_BYTES).text))
        except Exception:  # noqa: BLE001, S112  unreadable: nothing detected from it
            continue
    return texts


# -- one row ----------------------------------------------------------------------------------

def predict(row: dict[str, str], tags: list[str], scancode: Any, c_variant: v2.Variant,
            builtin: Any, http: v1.MemoHttp, settings: Any) -> dict[str, Any]:
    http.memo.clear()
    out: dict[str, Any] = {"row": int(row["row"]), "batch": row["batch"], "hf_id": row["hf_id"],
                           "sha": row["frozen_sha"], "expected": row["expected_status"].strip(),
                           "tags": tags}
    ref = f"hf:{row['hf_id']}@{row['frozen_sha']}"
    adapter = HuggingFaceAdapter(http)
    try:
        ds = adapter.resolve(ref)
        card = adapter.card(ds)
    except (DatasetNotFound, FetchError, ValueError) as exc:
        out["excluded"] = f"card not readable at the frozen sha: {exc}"[:300]
        return out
    out["A"] = baseline_a(tags)
    try:
        dets = [(label, d.expression, d.score) for label, text in
                scancode_texts(adapter, ds, card) for d in scancode.detect(text)
                if not d.versionless]
        out["B"] = baseline_b(tags, [e for _l, e, _s in dets])
        out["B_detections"] = dets
    except Exception as exc:  # noqa: BLE001  counts as unknown
        out["B"], out["B_error"] = "unknown", f"{type(exc).__name__}: {exc}"[:300]
    pipeline.get_scanner = lambda _choice: builtin  # type: ignore[assignment]
    with c_variant:
        try:
            report = pipeline.run_check(ref, settings, http=http)
            summ = next(r for r in report.results if r.check == "licence.summary")
            out["C"], out["C_sub"] = str(summ.status), summ.data.get("sub")
            out["C_comparisons"] = [{"check": r.check, "status": str(r.status),
                                     "sub": r.data.get("sub")} for r in report.results
                                    if r.check.startswith("licence.")
                                    and r.check != "licence.summary"]
        except Exception as exc:  # noqa: BLE001  counts as unknown, as in v1
            out["C"], out["C_error"] = "unknown", f"{type(exc).__name__}: {exc}"[:300]
    return out


def main() -> int:
    frozen_at = v2.check_frozen()
    rows = labelled_rows()
    cfg = yaml.safe_load(v2.CONFIG.read_text("utf-8"))
    tags_of = {d["id"]: d.get("license_tags") or []
               for d in json.loads(LIST.read_text("utf-8"))["datasets"]}
    scancode = v1.ScanCodeAt(SCANCODE_MIN)
    builtin = v2.builtin_scanner(cfg)
    (c_variant,) = v2.variants(cfg, "frozen")
    settings = v2.settings_from(cfg)
    http = v1.MemoHttp(v1.CACHE, host_interval=1.0)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "predictions.jsonl"
    done = set()
    if path.exists():
        done = {(r["batch"], r["hf_id"]) for r in map(json.loads, path.read_text(
            "utf-8").splitlines())}
    print(json.dumps({"frozen_at": frozen_at, "rows": len(rows), "hf_token": hf_token_present(),
                      "github_token": False, "B": scancode.describe(), "C": builtin.label,
                      "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}), flush=True)
    with open(path, "a", encoding="utf-8") as fh:
        for i, row in enumerate(rows, 1):
            if (row["batch"], row["hf_id"]) in done:
                continue
            rec = predict(row, tags_of.get(row["hf_id"], []), scancode, c_variant, builtin,
                          http, settings)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{i}/{len(rows)}] {row['hf_id']}", flush=True)
    http.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
