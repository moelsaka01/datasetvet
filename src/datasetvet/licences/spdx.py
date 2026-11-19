"""SPDX data and expressions: the vendored licence list, parse, normalise, compare. Task 3.2.

- `spdx_data()` loads `data/spdx_licences.json.gz` (official texts and flags from
  github.com/spdx/license-list-data at a pinned tag; built by `tools/vendor_spdx.py`).
- Expressions go through `license-expression` (Apache-2.0, from the ScanCode authors), so
  `GPL-2.0` and `GPL-2.0-only` are equivalent and `GPL-2.0-or-later` is not, as SPDX defines.
- Keys that are not on the SPDX list (HF's non-SPDX ids, ScanCode's `LicenseRef-scancode-*`)
  are kept as `LicenseRef-*` symbols and compared by name only.
"""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

from license_expression import ExpressionError, Licensing, get_spdx_licensing


@lru_cache(maxsize=1)
def spdx_data() -> dict[str, Any]:
    raw = resources.files("datasetvet.data").joinpath("spdx_licences.json.gz").read_bytes()
    data: dict[str, Any] = json.loads(gzip.decompress(raw))
    return data


def list_version() -> str:
    return str(spdx_data()["list_version"])


@lru_cache(maxsize=1)
def _ids_lower() -> dict[str, str]:
    return {k.lower(): k for k in spdx_data()["all_ids"]}


def spdx_id(value: str) -> str | None:
    """Case-insensitive lookup of one SPDX licence id: 'cc-by-nc-4.0' -> 'CC-BY-NC-4.0'."""
    return _ids_lower().get(value.strip().lower())


def flags(lid: str) -> tuple[bool, bool, bool] | None:
    """(OSI-approved, FSF-libre, deprecated id) from the SPDX list, or None if not listed."""
    f = spdx_data()["all_ids"].get(lid)
    return (bool(f[0]), bool(f[1]), bool(f[2])) if f else None


@lru_cache(maxsize=1)
def licensing() -> Licensing:
    return get_spdx_licensing()


_REF_RE = re.compile(r"^LicenseRef-[A-Za-z0-9.\-]+$")


def parse(expr: str) -> Any | None:
    """Parsed expression or None when it does not parse. Unknown keys are allowed only as
    LicenseRef-* (e.g. LicenseRef-hf-llama2)."""
    try:
        parsed = licensing().parse(expr)
    except ExpressionError:
        return None
    if parsed is None:
        return None
    for sym in licensing().license_symbols(parsed):
        key = sym.key
        if not _REF_RE.match(key) and licensing().validate(key).errors:
            return None
    return parsed


def normalise(expr: str) -> str | None:
    p = parse(expr)
    return None if p is None else str(p.render())


def keys(expr: str) -> set[str]:
    p = parse(expr)
    if p is None:
        return set()
    return {str(s.key) for s in licensing().license_symbols(p)}


def has_or(expr: str) -> bool:
    return bool(re.search(r"\bOR\b", expr, re.IGNORECASE))


@dataclass
class Relation:
    kind: str  # "equivalent", "subset", "differs", "unparsed"
    detail: str = ""


def relation(a: str, b: str) -> Relation:
    """How expression `a` relates to expression `b` (PLAN.md 5.2).

    equivalent: `license-expression` says so; subset: one side's keys are a strict subset of
    the other's (e.g. MIT vs MIT AND CC-BY-4.0); differs: anything else that parses.
    """
    pa, pb = parse(a), parse(b)
    if pa is None or pb is None:
        return Relation("unparsed", a if pa is None else b)
    if licensing().is_equivalent(pa, pb):
        return Relation("equivalent")
    ka, kb = keys(a), keys(b)
    if ka < kb:
        return Relation("subset", f"{a} is part of {b}")
    if kb < ka:
        return Relation("subset", f"{b} is part of {a}")
    return Relation("differs")
