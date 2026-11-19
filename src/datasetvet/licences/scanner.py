"""Licence-text scanners: the built-in matcher (always installed) and ScanCode (`[scan]`).

Task 3.4. Both return `matcher.Detection`s, so the checks never know which one ran. The report
records the scanner's name and version, and the Phase 4 evaluation runs each one separately.

- `builtin`: `licences/matcher.py`, against the vendored SPDX licence list. Deterministic.
- `scancode`: ScanCode toolkit (`pip install "datasetvet[scan]"`), detections with score
  >= SCANCODE_MIN_SCORE. Measured on Windows: needs `pluggy<1.6`, `typecode-libmagic`, a short
  venv path, and PowerShell rather than Git Bash (PLAN.md section 9).
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Protocol

from datasetvet.licences import matcher, spdx
from datasetvet.licences.matcher import Detection

SCANCODE_MIN_SCORE = 90.0  # PLAN.md 5.2; may only be tuned on the Phase 4 dev split


class Scanner(Protocol):
    name: str

    def describe(self) -> str: ...
    def detect(self, text: str) -> list[Detection]: ...


class BuiltinScanner:
    name = "builtin"

    def describe(self) -> str:
        return (f"built-in matcher (SPDX licence list {spdx.list_version()}; "
                f"full text dice >= {matcher.DICE_MIN:.2f}, containment >= "
                f"{matcher.CONTAIN_MIN:.2f}, exact names and URLs)")

    def detect(self, text: str) -> list[Detection]:
        return matcher.detect(text)


class ScanCodeUnavailable(RuntimeError):
    pass


class ScanCodeScanner:
    name = "scancode"

    def __init__(self, min_score: float = SCANCODE_MIN_SCORE):
        try:
            from scancode import api  # type: ignore[import-not-found]  # noqa: F401
        except Exception as exc:
            raise ScanCodeUnavailable(
                f"ScanCode is not installed or does not import ({type(exc).__name__}: {exc}); "
                'install it with pip install "datasetvet[scan]"') from exc
        self.min_score = min_score
        self._version = _scancode_version()

    def describe(self) -> str:
        return f"ScanCode toolkit {self._version} (detections with score >= {self.min_score:g})"

    def raw(self, text: str) -> dict[str, Any]:
        """ScanCode's own `get_licenses()` output for `text`, before any score threshold."""
        from scancode import api

        fd, path = tempfile.mkstemp(suffix=".txt", prefix="datasetvet-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            result: dict[str, Any] = api.get_licenses(location=path, include_text=True)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        return result

    def detect(self, text: str) -> list[Detection]:
        return scancode_detections(self.raw(text), self.min_score)


def scancode_detections(result: dict[str, Any], min_score: float) -> list[Detection]:
    """Map ScanCode's `get_licenses()` output (32.x) to Detections; kept separate for tests."""
    out: list[Detection] = []
    for det in result.get("license_detections") or []:
        matches = det.get("matches") or []
        if not matches:
            continue
        score = min(float(m.get("score", 0)) for m in matches)
        if score < min_score:
            continue
        expr = det.get("license_expression_spdx") or det.get("license_expression") or ""
        if not expr:
            continue
        first = min(int(m.get("start_line", 0)) for m in matches)
        last = max(int(m.get("end_line", 0)) for m in matches)
        text = " ".join(str(matches[0].get("matched_text", "")).split())[:120]
        out.append(Detection(expression=expr, method="scancode", score=round(score, 1),
                             lines=(first, last) if first else None, matched=text))
    return matcher.dedupe(out)


def _scancode_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    for dist in ("scancode-toolkit-mini", "scancode-toolkit"):
        try:
            return version(dist)
        except PackageNotFoundError:
            pass
    return "unknown version"


def scancode_available() -> bool:
    try:
        ScanCodeScanner()
    except ScanCodeUnavailable:
        return False
    return True


def get_scanner(choice: str = "auto") -> Scanner:
    """`builtin`, `scancode` (error if missing) or `auto` (ScanCode when it imports)."""
    if choice == "builtin":
        return BuiltinScanner()
    if choice == "scancode":
        return ScanCodeScanner()
    if choice == "auto":
        try:
            return ScanCodeScanner()
        except ScanCodeUnavailable:
            return BuiltinScanner()
    raise ValueError(f"unknown scanner {choice!r} (builtin, scancode or auto)")
