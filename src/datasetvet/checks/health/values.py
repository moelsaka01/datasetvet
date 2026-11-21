"""Arrow batches to Python values, for hashing and the empty-row check (PLAN.md 5.5).

`batch.to_pydict()` raises ValueError for a nanosecond timestamp that is not a whole number of
microseconds, because a Python `datetime` cannot hold it (pandas is not a dependency). Such
columns, at any depth inside structs and lists, are read as their integer count of
nanoseconds instead. Nothing is rounded, so two timestamps one nanosecond apart still differ
and rows are never wrongly called duplicates. Only the representation of those values changes;
the common case (no nanosecond column) is the plain `to_pydict()`.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa


def _has_ns(t: pa.DataType) -> bool:
    if pa.types.is_timestamp(t):
        return t.unit == "ns"
    if pa.types.is_struct(t):
        return any(_has_ns(t.field(i).type) for i in range(t.num_fields))
    if pa.types.is_list(t) or pa.types.is_large_list(t):
        return _has_ns(t.value_type)
    return False


def _ns_as_int(arr: pa.Array) -> pa.Array:
    t = arr.type
    if not _has_ns(t):
        return arr
    if pa.types.is_timestamp(t):
        return arr.cast(pa.int64())
    if pa.types.is_struct(t):
        kids = arr.flatten()  # children with the struct's offset applied
        return pa.StructArray.from_arrays([_ns_as_int(k) for k in kids],
                                          names=[t.field(i).name for i in range(t.num_fields)],
                                          mask=arr.is_null())
    cls = pa.LargeListArray if pa.types.is_large_list(t) else pa.ListArray
    return cls.from_arrays(arr.offsets, _ns_as_int(arr.values), mask=arr.is_null())


def batch_to_pydict(batch: pa.RecordBatch) -> dict[str, list[Any]]:
    """Like `batch.to_pydict()`, but nanosecond timestamps become integers (see module doc)."""
    if not any(_has_ns(f.type) for f in batch.schema):
        return batch.to_pydict()
    return {f.name: _ns_as_int(batch.column(i)).to_pylist()
            for i, f in enumerate(batch.schema)}
