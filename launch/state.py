"""Launch-scan state in SQLite (PLAN.md section 10, task 4.2): one row per (dataset, tier).

A row is finished when its status is `done` (a report was written) or `failed` (the check
raised; retried by `--retry-failed`). A finished row is skipped on resume only when its
revision and config hash match the current run, so changing settings re-runs everything.
Each row is committed on its own, so a crash or Ctrl-C loses at most the dataset in flight.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    dataset_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    sha TEXT,
    config_hash TEXT NOT NULL,
    status TEXT NOT NULL,          -- done / failed
    report TEXT,                   -- JSON report (datasetvet's schema)
    error TEXT,
    seconds REAL,
    http_requests INTEGER,
    finished_at TEXT NOT NULL,
    PRIMARY KEY (dataset_id, tier)
)
"""


class State:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=60)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(SCHEMA)
        self.db.commit()

    def finished(self, dataset_id: str, tier: str, sha: str | None, config_hash: str,
                 retry_failed: bool = False) -> bool:
        row = self.db.execute("SELECT sha, config_hash, status FROM runs WHERE dataset_id=? "
                              "AND tier=?", (dataset_id, tier)).fetchone()
        if row is None or row[0] != sha or row[1] != config_hash:
            return False
        return not (retry_failed and row[2] == "failed")

    def put(self, dataset_id: str, tier: str, sha: str | None, config_hash: str, status: str,
            report: str | None = None, error: str | None = None, seconds: float | None = None,
            http_requests: int | None = None) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
            (dataset_id, tier, sha, config_hash, status, report, error, seconds, http_requests,
             time.strftime("%Y-%m-%dT%H:%M:%S%z")))
        self.db.commit()

    def rows(self, tier: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM runs" + (" WHERE tier=?" if tier else "") + " ORDER BY dataset_id"
        cur = self.db.execute(q, (tier,) if tier else ())
        names = [c[0] for c in cur.description]
        return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]

    def close(self) -> None:
        self.db.close()
