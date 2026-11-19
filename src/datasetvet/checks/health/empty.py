"""Empty rows and corrupt files (PLAN.md 5.5). Task 2.10.

A row is empty when every column is null, an empty string, an empty list or an empty struct
whose fields are all empty. Whitespace-only strings are not empty under this rule.
A corrupt file is one that fails to download, open or decode; it is reported with its path and
error, the scan carries on, and the split's other results are marked partial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EXAMPLES = 5


def is_empty_value(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str | bytes | list | tuple):
        return len(v) == 0
    if isinstance(v, dict):
        return all(is_empty_value(x) for x in v.values())
    return False


@dataclass
class EmptyCounter:
    count: int = 0
    examples: list[list[int]] = field(default_factory=list)

    def add_columns(self, columns: dict[str, list[Any]], file_no: int, first_row: int) -> None:
        names = list(columns)
        if not names:
            return
        n = len(columns[names[0]])
        for i in range(n):
            if all(is_empty_value(columns[c][i]) for c in names):
                self.count += 1
                if len(self.examples) < EXAMPLES:
                    self.examples.append([file_no, first_row + i])


@dataclass
class CorruptFile:
    split: str
    path: str
    error: str
