"""Empty rows and files that could not be read as rows (PLAN.md 5.5). Task 2.10.

A row is empty when every column is null, an empty string, an empty list or an empty struct
whose fields are all empty. Whitespace-only strings are not empty under this rule.

A file "could not be read as rows" when it fails to download, open or decode into a table. That
is not the same as a damaged file: the reader needs one type per column, and a data folder may
hold files that are not tables. Each failure is reported with its path, its error and a kind
(`classify_error`); the scan carries on and the split's other results are marked partial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EXAMPLES = 5

# What each kind of failure means, in the words of the report.
KIND_LABELS = {
    "invalid": "the content is not valid for its file type",
    "reader_limit": "datasetvet's reader needs one type per column and could not fit this "
                    "file into a table",
    "empty": "the file has no rows",
    "download": "the download failed",
}


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
class UnreadableFile:
    split: str
    path: str
    error: str
    kind: str  # a key of KIND_LABELS


_TYPE_CLASH = ("changed from", "cannot mix", "could not convert", "straddles", "expected bytes",
               "tried to convert", "to a struct", "mixes")


def classify_error(exc: BaseException) -> str:
    """Which kind of "could not be read as rows" an exception is (see KIND_LABELS)."""
    from datasetvet.http import FetchError  # local: keep this module free of the HTTP layer

    if isinstance(exc, FetchError):
        return "download"
    text = str(exc).lower()
    if "empty json file" in text or "document is empty" in text:
        return "empty"
    name = type(exc).__name__
    if name == "ArrowTypeError" or (name in ("ArrowInvalid", "ArrowNotImplementedError")
                                    and any(m in text for m in _TYPE_CLASH)):
        return "reader_limit"
    return "invalid"
