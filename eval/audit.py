"""The human disagreement audit (PLAN.md section 8, Phase 5): labels -> the RESULTS.md table.

The owner labels each row of eval/results/disagreements-<scanner>.csv in the column
`owner_label (ours wrong / key wrong / changed since audit / ambiguous)`. This reads the two
files and prints the "Human audit" table, one row per scanner, never pooled.

    python eval/audit.py            print the markdown table (refuses while rows are unlabelled)
    python eval/audit.py --partial  print what is labelled so far, saying how many are missing

Labels are matched on their first word, case-insensitively: ours / datasetvet, key, changed,
ambiguous. Anything else is an error, not a guess.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

RES = Path(__file__).resolve().parent / "results"
SCANNERS = ("builtin", "scancode")
LABELS = {
    "ours": "datasetvet's fault",
    "key": "the key's fault",
    "changed": "changed since the audit",
    "ambiguous": "ambiguous",
}
FIRST_WORDS = {"ours": "ours", "datasetvet": "ours", "datasetvet's": "ours", "key": "key",
               "the": "key", "changed": "changed", "ambiguous": "ambiguous"}


class AuditError(ValueError):
    pass


def label_of(raw: str) -> str | None:
    text = raw.strip().lower()
    if not text:
        return None
    first = text.replace("'", "").replace("-", " ").split()[0].strip(".,;:")
    first = {"datasetvets": "datasetvet"}.get(first, first)
    if first == "the" and "key" in text:
        return "key"
    if first not in FIRST_WORDS:
        raise AuditError(f"unknown label {raw!r}: use ours wrong / key wrong / "
                         "changed since audit / ambiguous")
    return FIRST_WORDS[first]


def tally(path: Path) -> tuple[Counter[str], int]:
    """(labelled counts, number of rows)."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    col = next(c for c in rows[0] if c.startswith("owner_label"))
    counts: Counter[str] = Counter()
    for r in rows:
        lab = label_of(r[col])
        if lab:
            counts[lab] += 1
    return counts, len(rows)


def table(partial: bool = False) -> str:
    lines = ["| scanner | rows labelled | " + " | ".join(LABELS.values()) + " |",
             "|---|---|" + "---|" * len(LABELS)]
    missing = 0
    data = {}
    for s in SCANNERS:
        counts, n = tally(RES / f"disagreements-{s}.csv")
        done = sum(counts.values())
        missing += n - done
        data[s] = {"rows": n, "labelled": done, **{k: counts[k] for k in LABELS}}
        cells = " | ".join(f"{counts[k]} ({counts[k] / done:.0%})" if done else "-"
                           for k in LABELS)
        lines.append(f"| {'built-in matcher' if s == 'builtin' else 'ScanCode (≥ 50)'} | "
                     f"{done} of {n} | {cells} |")
    if missing and not partial:
        raise AuditError(f"{missing} row(s) are not labelled yet (use --partial to see the rest)")
    if not missing:  # the counts are only recorded once every row is labelled
        (RES / "audit.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8",
                                        newline="\n")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    try:
        print(table(partial="--partial" in sys.argv))
    except AuditError as exc:
        raise SystemExit(f"audit: {exc}") from exc
