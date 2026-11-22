"""eval/audit.py: labels in, the "Human audit" table out; nothing is guessed."""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
import audit

COL = "owner_label (ours wrong / key wrong / changed since audit / ambiguous)"


def write(path: Path, labels: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["hf_id", COL, "notes"])
        w.writeheader()
        for i, lab in enumerate(labels):
            w.writerow({"hf_id": f"o/d{i}", COL: lab, "notes": ""})


@pytest.mark.parametrize("raw,expected", [
    ("ours wrong", "ours"), ("Ours", "ours"), ("datasetvet's fault", "ours"),
    ("key wrong", "key"), ("Key", "key"), ("the key's fault", "key"),
    ("changed since audit", "changed"), ("changed", "changed"),
    ("ambiguous", "ambiguous"), ("  Ambiguous. ", "ambiguous"), ("", None), ("  ", None),
])
def test_label_of(raw, expected):
    assert audit.label_of(raw) == expected


def test_an_unknown_label_is_an_error_not_a_guess():
    with pytest.raises(audit.AuditError, match="unknown label"):
        audit.label_of("probably fine")


def test_tally_and_table(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "RES", tmp_path)
    write(tmp_path / "disagreements-builtin.csv",
          ["ours wrong"] * 12 + ["key wrong"] * 10 + ["changed since audit"] * 5 + ["ambiguous"] * 3)
    write(tmp_path / "disagreements-scancode.csv",
          ["ours wrong"] * 15 + ["key wrong"] * 9 + ["changed since audit"] * 4 + ["ambiguous"] * 2)
    out = audit.table()
    assert "| built-in matcher | 30 of 30 | 12 (40%) | 10 (33%) | 5 (17%) | 3 (10%) |" in out
    assert "| ScanCode (≥ 50) | 30 of 30 | 15 (50%) | 9 (30%) | 4 (13%) | 2 (7%) |" in out


def test_unlabelled_rows_block_the_table_unless_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "RES", tmp_path)
    write(tmp_path / "disagreements-builtin.csv", ["ours wrong", "", "key wrong"])
    write(tmp_path / "disagreements-scancode.csv", ["", "", ""])
    with pytest.raises(audit.AuditError, match="4 row"):
        audit.table()
    out = audit.table(partial=True)
    assert "| built-in matcher | 2 of 3 | 1 (50%) | 1 (50%) | 0 (0%) | 0 (0%) |" in out
    assert "| ScanCode (≥ 50) | 0 of 3 | - | - | - | - |" in out
