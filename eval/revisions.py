"""Audit-time card revision (PLAN.md section 8, task 4.4).

The DPI recorded what each card said (`HF Yaml License`) when it collected its metadata. We
read the card as it was then: the latest commit on `main` dated on or before the DPI audit date
(eval/build_key.py: the last commit touching the repo's summary file in the DPI repo).

`/api/datasets/{id}/commits/main?p=N` lists commits newest first; renamed repos redirect.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from datasetvet.http import Http

HUB = "https://huggingface.co"
MAX_PAGES = 40


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def audit_revision(http: Http, hf_id: str, audit_date: str) -> dict[str, Any]:
    """{'sha', 'date', 'note'} for the latest commit at or before audit_date, or
    {'sha': None, 'note': why}."""
    target = _ts(audit_date)
    newest = None
    for page in range(MAX_PAGES):
        resp = http.get(f"{HUB}/api/datasets/{hf_id}/commits/main",
                        params={"p": str(page)} if page else None)
        if resp.status in (401, 403, 404):
            return {"sha": None, "note": f"commits not readable (HTTP {resp.status})"}
        if not resp.ok:
            return {"sha": None, "note": f"commits API HTTP {resp.status}"}
        commits = resp.json()
        if not commits:
            break
        newest = newest or commits[0]["date"]
        for c in commits:
            if _ts(c["date"]) <= target:
                return {"sha": c["id"], "date": c["date"], "note": "",
                        "renamed": bool(resp.history), "newest": newest}
        if "rel=\"next\"" not in resp.headers.get("link", "") and len(commits) < 50:
            break
    return {"sha": None, "note": "no commit on main at or before the audit date "
                                 f"({audit_date[:10]}; oldest commit is later)"}


class RevisionCache:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = (json.loads(path.read_text("utf-8"))
                                     if path.exists() else {})

    def get(self, http: Http, hf_id: str, audit_date: str) -> dict[str, Any]:
        key = f"{hf_id}@{audit_date}"
        if key not in self.data:
            self.data[key] = audit_revision(http, hf_id, audit_date)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True), "utf-8")
            tmp.replace(self.path)
        result: dict[str, Any] = self.data[key]
        return result
