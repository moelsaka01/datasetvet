"""Canonical row encoding and xxh3_128 row/input hashes (PLAN.md 5.5). Task 2.7.

Encoding: columns in sorted name order, each as (name, value); every value is type-tagged so
1, 1.0, "1", True and b"1" all differ. Floats are their IEEE-754 double bits. Nested lists and
structs are encoded recursively; images and audio arrive as structs holding raw bytes.

Two hashes per row: `row` over all columns, and `input` over all columns except the label
columns, so "same input, different label" across splits can be found.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import struct
from collections.abc import Iterable, Sequence
from typing import Any

import xxhash

_LEN = struct.Struct("<Q")
_F64 = struct.Struct("<d")

# Birthday bound for 128-bit hashes at 1e9 rows: n^2 / 2^129.
COLLISION_NOTE = ("rows are compared by 128-bit xxh3 hashes; the chance of any false match is "
                  "about 1.5e-21 at one billion rows")


def _enc(v: Any, out: list[bytes]) -> None:
    if v is None:
        out.append(b"N")
    elif v is True:
        out.append(b"B\x01")
    elif v is False:
        out.append(b"B\x00")
    elif isinstance(v, int):
        s = str(v).encode()
        out.append(b"I" + _LEN.pack(len(s)) + s)
    elif isinstance(v, float):
        out.append(b"F" + _F64.pack(v))
    elif isinstance(v, str):
        s = v.encode("utf-8", "surrogatepass")
        out.append(b"S" + _LEN.pack(len(s)) + s)
    elif isinstance(v, bytes | bytearray | memoryview):
        b = bytes(v)
        out.append(b"Y" + _LEN.pack(len(b)) + b)
    elif isinstance(v, dict):
        out.append(b"D" + _LEN.pack(len(v)))
        for k in sorted(v, key=str):
            _enc(str(k), out)
            _enc(v[k], out)
    elif isinstance(v, list | tuple):
        out.append(b"L" + _LEN.pack(len(v)))
        for item in v:
            _enc(item, out)
    elif isinstance(v, _dt.datetime | _dt.date | _dt.time | _dt.timedelta | decimal.Decimal):
        s = f"{type(v).__name__}:{v.isoformat() if hasattr(v, 'isoformat') else v}".encode()
        out.append(b"T" + _LEN.pack(len(s)) + s)
    else:
        s = f"{type(v).__module__}.{type(v).__qualname__}:{v!r}".encode()
        out.append(b"O" + _LEN.pack(len(s)) + s)


def encode_value(v: Any) -> bytes:
    out: list[bytes] = []
    _enc(v, out)
    return b"".join(out)


def encode_row(row: dict[str, Any], columns: Iterable[str] | None = None) -> bytes:
    cols = sorted(row) if columns is None else sorted(columns)
    out: list[bytes] = []
    for c in cols:
        _enc(c, out)
        _enc(row.get(c), out)
    return b"".join(out)


def hash_row(row: dict[str, Any], columns: Iterable[str] | None = None) -> bytes:
    return xxhash.xxh3_128_digest(encode_row(row, columns))


def hash_columns(columns: dict[str, Sequence[Any]], label_columns: Iterable[str] = (),
                 ) -> tuple[list[bytes], list[bytes]]:
    """Hash a batch given as {column: values}. Returns (row hashes, input hashes)."""
    names = sorted(columns)
    labels = set(label_columns)
    n = len(columns[names[0]]) if names else 0
    # encode each column once, then join per row
    encoded = {c: [encode_value(c) + encode_value(v) for v in columns[c]] for c in names}
    input_names = [c for c in names if c not in labels]
    rows_h: list[bytes] = []
    inputs_h: list[bytes] = []
    digest = xxhash.xxh3_128_digest
    same = len(input_names) == len(names)
    for i in range(n):
        rh = digest(b"".join(encoded[c][i] for c in names))
        rows_h.append(rh)
        inputs_h.append(rh if same else digest(b"".join(encoded[c][i] for c in input_names)))
    return rows_h, inputs_h
