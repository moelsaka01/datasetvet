"""JSON report with schema_version: the single source of truth (PLAN.md section 7). Task 2.12."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datasetvet.model import Report


def to_json(report: Report, indent: int = 2) -> str:
    return json.dumps(report.to_dict(), indent=indent, ensure_ascii=False, default=_default)


def _default(obj: Any) -> Any:
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, set | tuple):
        return list(obj)
    raise TypeError(f"not JSON serialisable: {type(obj).__name__}")


def write_json(report: Report, path: str | Path) -> None:
    Path(path).write_text(to_json(report) + "\n", encoding="utf-8")


def read_json(path: str | Path) -> Report:
    return Report.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
