"""Published licence properties only: SPDX flags and Creative Commons elements. Task 3.3.

- From the SPDX licence list (vendored, `spdx.list_version()`): OSI-approved, FSF-libre,
  deprecated id.
- For Creative Commons licences only: the elements BY / SA / NC / ND, which are part of each
  licence's published name; `data/cc_elements.csv` has the deed URL per row.
- Nothing else. Properties are shown next to a licence and never decide a status.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from datasetvet.licences import spdx

CC_NAMES = {"BY": "Attribution", "SA": "ShareAlike", "NC": "NonCommercial",
            "ND": "NoDerivatives"}


@dataclass
class Properties:
    licence: str
    osi: bool | None = None
    fsf: bool | None = None
    deprecated: bool | None = None
    cc_elements: list[str] = field(default_factory=list)
    cc_deed: str | None = None
    on_spdx_list: bool = False

    def text(self) -> str:
        if not self.on_spdx_list:
            return f"{self.licence}: not on the SPDX list (no published properties)"
        parts = []
        if self.cc_deed is not None:
            els = ", ".join(f"{e} ({CC_NAMES[e]})" for e in self.cc_elements)
            parts.append(f"CC elements {els}" if els else "CC public-domain dedication")
        parts.append("OSI-approved" if self.osi else "not OSI-approved")
        parts.append("FSF-libre" if self.fsf else "not marked FSF-libre")
        if self.deprecated:
            parts.append("deprecated SPDX id")
        return f"{self.licence}: " + "; ".join(parts) + f" (SPDX list {spdx.list_version()})"

    def as_dict(self) -> dict[str, object]:
        return {"licence": self.licence, "on_spdx_list": self.on_spdx_list, "osi": self.osi,
                "fsf": self.fsf, "deprecated": self.deprecated,
                "cc_elements": self.cc_elements, "cc_deed": self.cc_deed}


@lru_cache(maxsize=1)
def cc_table() -> dict[str, tuple[list[str], str]]:
    text = resources.files("datasetvet.data").joinpath("cc_elements.csv").read_text("utf-8")
    return {r["spdx"]: ([e for e in r["elements"].split(";") if e], r["deed_url"])
            for r in csv.DictReader(text.splitlines())}


def properties(licence: str) -> Properties:
    f = spdx.flags(licence)
    if f is None:
        return Properties(licence)
    p = Properties(licence, osi=f[0], fsf=f[1], deprecated=f[2], on_spdx_list=True)
    if licence in cc_table():
        p.cc_elements, p.cc_deed = cc_table()[licence]
    return p
