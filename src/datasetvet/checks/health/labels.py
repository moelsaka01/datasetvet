"""Label balance per split (PLAN.md 5.5). Task 2.10.

Label columns: ClassLabel features (from the Parquet file's Hugging Face metadata, else the
card's dataset_info), else columns named `label` or `labels`. Counts and shares per label, the
max/min ratio, and labels present in a non-train split but absent from train. No verdict such
as "imbalanced" is given.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

MAX_DISTINCT = 1000
FALLBACK_NAMES = ("label", "labels")


def labels_from_hf_features(features: Any) -> dict[str, list[str]]:
    """{column: class names} for ClassLabel (or list-of-ClassLabel) features."""
    out: dict[str, list[str]] = {}
    if not isinstance(features, dict):
        return out
    for name, feat in features.items():
        names = _classlabel(feat)
        if names is not None:
            out[name] = names
    return out


def _classlabel(feat: Any) -> list[str] | None:
    if isinstance(feat, dict):
        if feat.get("_type") == "ClassLabel":
            return [str(n) for n in feat.get("names") or []]
        if feat.get("_type") in ("Sequence", "List", "LargeList"):
            return _classlabel(feat.get("feature"))
    if isinstance(feat, list) and len(feat) == 1:  # [ClassLabel] shorthand
        return _classlabel(feat[0])
    return None


def pick_label_columns(schema_names: list[str], classlabels: dict[str, list[str]],
                       ) -> tuple[list[str], str]:
    cols = [c for c in classlabels if c in schema_names]
    if cols:
        return cols, "ClassLabel feature"
    cols = [c for c in schema_names if c.lower() in FALLBACK_NAMES]
    return cols, ("column named label/labels" if cols else "none")


@dataclass
class LabelCounter:
    names: list[str] | None = None
    counts: Counter = field(default_factory=Counter)
    too_many: bool = False
    rows: int = 0

    def add(self, arr: pa.Array | pa.ChunkedArray) -> None:
        self.rows += len(arr)
        if self.too_many:
            return
        if pa.types.is_list(arr.type) or pa.types.is_large_list(arr.type):
            arr = pc.list_flatten(arr)
        for item in pc.value_counts(arr).to_pylist():
            v = item["values"]
            key = v if isinstance(v, str | int | float | bool) or v is None else repr(v)
            self.counts[key] += item["counts"]
        if len(self.counts) > MAX_DISTINCT:
            self.too_many = True
            self.counts.clear()

    def no_label_values(self) -> set[Any]:
        """ClassLabel uses -1 for "no label"; for other label columns only null counts."""
        return {-1, None} if self.names else {None}

    def display(self, value: Any) -> str:
        if value is None:
            return "(null)"
        if self.names and isinstance(value, int) and not isinstance(value, bool):
            if 0 <= value < len(self.names):
                return self.names[value]
            if value == -1:
                return "-1 (no label)"
        return str(value)

    def table(self) -> list[dict[str, Any]]:
        total = sum(self.counts.values())
        return [{"label": self.display(k), "value": k, "count": n,
                 "share": (n / total if total else 0.0)}
                for k, n in sorted(self.counts.items(), key=lambda kv: (-kv[1], str(kv[0])))]

    def ratio(self) -> float | None:
        vals = [n for k, n in self.counts.items() if k not in self.no_label_values()]
        if len(vals) < 2 or min(vals) == 0:
            return None
        return max(vals) / min(vals)
