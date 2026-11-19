"""Build the answer key from the Data Provenance Initiative's data summaries (PLAN.md section 8).

Usage:  python eval/build_key.py [DPI_CLONE]   (default eval/cache/dpi)

The clone is github.com/Data-Provenance-Initiative/Data-Provenance-Collection (Apache-2.0),
checked out at DPI_SHA with `data_summaries/`. Writes eval/key/key.json (one row per HF repo)
and eval/key/key_stats.json. Every rule below was fixed before any result was computed.

1. DPI licence names -> SPDX via eval/dpi_licence_map.csv (spdx / none / non-spdx).
2. One row per HF repo; a repo is dropped when its DPI entries disagree on the expert licence
   set or on the recorded card licence (`HF Yaml License`).
3. Expert set: the entry's `Licenses`, mapped; `none` members are dropped when other licences
   are present. Any `non-spdx` member -> excluded from Q3 ("expert non-SPDX"); only `none`
   -> excluded ("expert none").
4. Expected status: card at audit time (`HF Yaml License`) vs expert set. Empty / Unspecified
   -> `missing`; a non-SPDX card value -> excluded ("card non-SPDX"); otherwise `consistent`
   when the expressions are equivalent (license-expression), else `inconsistent`.
5. Audit date: the last commit touching the repo's summary file(s) in the DPI repo (latest
   when several files name the repo). The card revision is chosen in eval/revisions.py.
6. Split: sha256(lower-cased HF id) % 100 < 30 -> dev, else test.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from datasetvet.licences import spdx

DPI_REPO = "https://github.com/Data-Provenance-Initiative/Data-Provenance-Collection"
DPI_SHA = "ce6662deccf011574427b6f112df479d261960b8"
MAP = ROOT / "eval" / "dpi_licence_map.csv"
OUT = ROOT / "eval" / "key"
DEV_PERCENT = 30
_HF_RE = re.compile(r"huggingface\.co/datasets/([^/\s?#]+(?:/[^/\s?#]+)?)", re.IGNORECASE)


def licence_map() -> dict[str, tuple[str, str]]:
    with open(MAP, encoding="utf-8") as fh:
        return {r["dpi_name"]: (r["kind"], r["spdx"]) for r in csv.DictReader(fh)}


def split_of(hf_id: str) -> str:
    h = int(hashlib.sha256(hf_id.lower().encode()).hexdigest(), 16)
    return "dev" if h % 100 < DEV_PERCENT else "test"


def hf_id_of(entry: dict[str, Any]) -> str | None:
    m = _HF_RE.search(entry.get("Hugging Face URL") or "")
    if m:
        return m.group(1).rstrip("/")
    im = entry.get("Inferred Metadata") or {}
    return im.get("HF Dataset") or None


def expert_set(names: list[str], lmap: dict[str, tuple[str, str]]) -> tuple[str, list[str]]:
    """('spdx', ids) / ('none', []) / ('non-spdx', [names]) / ('unmapped', [names])."""
    kinds = []
    for n in names:
        if n not in lmap:
            return "unmapped", [n]
        kinds.append((lmap[n][0], lmap[n][1] or n))
    if any(k == "non-spdx" for k, _ in kinds):
        return "non-spdx", sorted({v for k, v in kinds if k == "non-spdx"})
    ids = sorted({v for k, v in kinds if k == "spdx"})
    return ("spdx", ids) if ids else ("none", [])


def yaml_value(raw: str | None, lmap: dict[str, tuple[str, str]]) -> tuple[str, str | None]:
    """DPI's recorded card licence -> ('missing', None) / ('spdx', id) / ('non-spdx', name)."""
    if not raw or raw == "Unspecified":
        return "missing", None
    kind, sid = lmap.get(raw, ("unmapped", ""))
    return ("spdx", sid) if kind == "spdx" else (kind, raw)


def expected(card: tuple[str, str | None], expert: tuple[str, list[str]]) -> tuple[str | None,
                                                                                    str]:
    """(expected status or None, exclusion reason)."""
    ek, ev = expert
    if ek in ("non-spdx", "unmapped"):
        return None, "expert licence not on the SPDX list (" + ", ".join(ev) + ")"
    if ek == "none":
        return None, "expert licence: none stated"
    ck, cv = card
    if ck == "missing":
        return "missing", ""
    if ck != "spdx" or not cv:
        return None, f"card licence at audit time not on the SPDX list ({cv})"
    rel = spdx.relation(cv, " AND ".join(ev))
    return ("consistent" if rel.kind == "equivalent" else "inconsistent"), ""


def file_dates(clone: Path) -> dict[str, str]:
    out = {}
    for f in sorted((clone / "data_summaries").glob("*.json")):
        rel = f.relative_to(clone).as_posix()
        out[f.name] = subprocess.run(["git", "-C", str(clone), "log", "-1", "--format=%cI",
                                      DPI_SHA, "--", rel], capture_output=True, text=True,
                                     check=True).stdout.strip()
    return out


def main(clone: Path) -> None:
    head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    if head != DPI_SHA:
        raise SystemExit(f"{clone} is at {head}, expected {DPI_SHA}")
    lmap = licence_map()
    dates = file_dates(clone)
    by_repo: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    n_entries = n_hf = 0
    unmapped: Counter[str] = Counter()
    for f in sorted((clone / "data_summaries").glob("*.json")):
        for e in json.loads(f.read_text("utf-8")).values():
            n_entries += 1
            for lic in e.get("Licenses") or []:
                if lic.get("License") not in lmap:
                    unmapped[lic.get("License")] += 1
            hf = hf_id_of(e)
            if hf:
                n_hf += 1
                by_repo[hf].append((f.name, e))
    rows = []
    dropped: Counter[str] = Counter()
    for hf in sorted(by_repo, key=str.lower):
        ents = by_repo[hf]
        experts = {tuple(sorted(lic["License"] for lic in e.get("Licenses") or []))
                   for _f, e in ents}
        yamls = {(e.get("Inferred Metadata") or {}).get("HF Yaml License") for _f, e in ents}
        if len({(k, tuple(v)) for k, v in (expert_set(list(x), lmap) for x in experts)}) > 1:
            dropped["entries disagree on the expert licence set"] += 1
            continue
        if len(yamls) > 1:
            dropped["entries disagree on the recorded card licence"] += 1
            continue
        if None in yamls:
            dropped["no Inferred Metadata (no recorded card licence)"] += 1
            continue
        names = list(next(iter(experts)))
        ex = expert_set(names, lmap)
        raw_yaml = next(iter(yamls))
        card = yaml_value(raw_yaml, lmap)
        status, why = expected(card, ex)
        im = ents[0][1].get("Inferred Metadata") or {}
        rows.append({
            "hf_id": hf,
            "split": split_of(hf),
            "dpi_entries": sorted(e["Unique Dataset Identifier"] for _f, e in ents),
            "dpi_files": sorted({f for f, _e in ents}),
            "audit_date": max(dates[f] for f, _e in ents),
            "dpi_licences": names,
            "expert_kind": ex[0],
            "expert": ex[1],
            "dpi_card_licence": raw_yaml,
            "card_kind": card[0],
            "card_spdx": card[1] if card[0] == "spdx" else None,
            "expected": status,
            "excluded": why or None,
            "dpi_github_licence": im.get("GitHub License") or None,
            "github_url": ents[0][1].get("GitHub URL") or None,
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "key.json").write_text(json.dumps({
        "source": f"{DPI_REPO}/tree/{DPI_SHA}/data_summaries",
        "source_licence": "Apache-2.0 (the DPI repository's licence)",
        "rows": rows}, indent=1, ensure_ascii=False) + "\n", "utf-8")
    inc = [r for r in rows if r["expected"]]
    stats = {
        "dpi_sha": DPI_SHA,
        "summary_files": len(dates),
        "entries": n_entries,
        "entries_with_hf_repo": n_hf,
        "unique_hf_repos": len(by_repo),
        "repos_dropped": dict(dropped),
        "key_rows": len(rows),
        "excluded_from_q3": dict(Counter(r["excluded"].split(" (")[0] for r in rows
                                         if r["excluded"])),
        "q3_rows": len(inc),
        "q3_expected": dict(Counter(r["expected"] for r in inc)),
        "q3_by_split": {s: dict(Counter(r["expected"] for r in inc if r["split"] == s))
                        for s in ("dev", "test")},
        "unmapped_licence_names": dict(unmapped),
    }
    (OUT / "key_stats.json").write_text(json.dumps(stats, indent=1) + "\n", "utf-8")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "eval" / "cache" / "dpi")
