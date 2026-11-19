"""Limits and settings from flags and environment (PLAN.md 5.4, 5.5). Task 2.12.

Precedence: command-line flag > environment variable (DATASETVET_*) > default.
A config file is not supported yet.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_UNITS = {"": 1, "B": 1, "KB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12,
          "KIB": 2**10, "MIB": 2**20, "GIB": 2**30, "TIB": 2**40}


def parse_bytes(text: str | int) -> int:
    """'5GB' -> 5_000_000_000 (decimal units; KiB/MiB/GiB are binary)."""
    if isinstance(text, int):
        return text
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]*)\s*", text)
    if not m or m.group(2).upper() not in _UNITS:
        raise ValueError(f"not a byte size: {text!r} (examples: 500MB, 5GB, 2GiB)")
    return int(float(m.group(1)) * _UNITS[m.group(2).upper()])


def default_cache_dir() -> Path:
    env = os.environ.get("DATASETVET_CACHE_DIR")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    return Path(base) / "datasetvet" if base else Path.home() / ".cache" / "datasetvet"


@dataclass
class Settings:
    max_scan_bytes: int = 5 * 10**9
    sample_rows: int = 1_000_000
    seed: int = 0
    full: bool = False  # force a full scan above max_scan_bytes
    check_data: bool = True
    check_links: bool = True
    configs: list[str] | None = None  # None = every config
    phone_region: str | None = None
    link_timeout: float = 15.0
    link_retries: int = 2
    max_links: int = 200
    duckdb_memory: str = "1GB"
    cache_dir: Path = field(default_factory=default_cache_dir)
    use_cache: bool = True

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d["cache_dir"] = None  # a local path is not part of the report
        return d


def from_env(base: Settings | None = None) -> Settings:
    s = base or Settings()
    env = os.environ
    if "DATASETVET_MAX_SCAN_BYTES" in env:
        s.max_scan_bytes = parse_bytes(env["DATASETVET_MAX_SCAN_BYTES"])
    if "DATASETVET_SAMPLE_ROWS" in env:
        s.sample_rows = int(env["DATASETVET_SAMPLE_ROWS"])
    if "DATASETVET_SEED" in env:
        s.seed = int(env["DATASETVET_SEED"])
    if "DATASETVET_PHONE_REGION" in env:
        s.phone_region = env["DATASETVET_PHONE_REGION"]
    if "DATASETVET_DUCKDB_MEMORY" in env:
        s.duckdb_memory = env["DATASETVET_DUCKDB_MEMORY"]
    return s
