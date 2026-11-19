"""HF licence id -> SPDX id / family / non-SPDX, from data/hf_licence_ids.csv. Task 3.1.

The table is HF's published list (hub-docs `repositories-licenses.md`, pinned commit in each
row's `source`), one row per id. `kind` is one of:
- `spdx`: maps to one SPDX licence id;
- `family`: a family, not a specific licence (bsd, cc, gpl, ...): every comparison is unknown;
- `non-spdx`: a named licence that is not on the SPDX list (llama2, openrail++, ...);
- `special`: `unknown` (no licence stated) or `other` (named in `license_name`).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from datasetvet.licences import spdx


@dataclass(frozen=True)
class HfLicence:
    value: str  # as written on the card
    kind: str  # spdx / family / non-spdx / special / spdx-not-hf / not-hf
    spdx: str | None  # SPDX id when kind is spdx or spdx-not-hf
    name: str  # HF's full name, or the SPDX name
    note: str = ""
    hf_id: str | None = None

    @property
    def expression_key(self) -> str | None:
        """The key used in comparisons: an SPDX id, or LicenseRef-hf-<id> for non-SPDX ids."""
        if self.spdx:
            return self.spdx
        if self.kind == "non-spdx" and self.hf_id:
            return "LicenseRef-hf-" + re.sub(r"[^A-Za-z0-9.\-]", "-", self.hf_id)
        return None


@lru_cache(maxsize=1)
def table() -> dict[str, dict[str, str]]:
    text = resources.files("datasetvet.data").joinpath("hf_licence_ids.csv").read_text("utf-8")
    return {row["hf_id"]: row for row in csv.DictReader(text.splitlines())}


def source_url() -> str:
    return next(iter(table().values()))["source"]


def lookup(value: str) -> HfLicence:
    v = value.strip()
    row = table().get(v) or table().get(v.lower())
    if row:
        sid = row["spdx"] or None
        return HfLicence(value=v, kind=row["kind"], spdx=sid, name=row["hf_name"],
                         note=row["note"], hf_id=row["hf_id"])
    sid = spdx.spdx_id(v)
    if sid:
        name = spdx.spdx_data()["licences"].get(sid, {}).get("name", sid)
        return HfLicence(value=v, kind="spdx-not-hf", spdx=sid, name=name,
                         note="not an HF licence id, but an SPDX id")
    return HfLicence(value=v, kind="not-hf", spdx=None, name=v,
                     note="neither an HF licence id nor an SPDX id")
