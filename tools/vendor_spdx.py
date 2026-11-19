"""Vendor official SPDX licence texts for the built-in matcher (PLAN.md section 4).

Usage:  python tools/vendor_spdx.py DOWNLOAD_DIR
Downloads licenses.json and text/<id>.txt from github.com/spdx/license-list-data at TAG into
DOWNLOAD_DIR, then writes src/datasetvet/data/spdx_licences.json.gz. Re-run to update the
pinned list version; the tests check that every SPDX id in hf_licence_ids.csv has a text.
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
import urllib.request
from pathlib import Path

TAG = "v3.29.0"
BASE = f"https://raw.githubusercontent.com/spdx/license-list-data/{TAG}"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "datasetvet" / "data" / "spdx_licences.json.gz"
HF_TABLE = ROOT / "src" / "datasetvet" / "data" / "hf_licence_ids.csv"

# Licences with a text in the matcher beyond the ones HF's id list maps to: other versions of
# the same families, and licences seen on data repos. The deprecated HF targets (GPL-2.0 ...)
# are replaced by their -only / -or-later successors, which carry the text.
EXTRA = [
    "CC-BY-1.0", "CC-BY-3.0-IGO", "CC-BY-SA-1.0", "CC-BY-SA-2.0", "CC-BY-SA-2.5", "CC-BY-NC-1.0",
    "CC-BY-NC-2.5", "CC-BY-ND-1.0", "CC-BY-ND-2.0", "CC-BY-ND-2.5", "CC-BY-ND-3.0",
    "CC-BY-NC-ND-1.0", "CC-BY-NC-ND-2.0", "CC-BY-NC-ND-2.5", "CC-BY-NC-SA-1.0", "CC-BY-NC-SA-2.5",
    "CC-PDDC", "ODC-By-1.0", "ODbL-1.0", "O-UDA-1.0", "OGL-UK-3.0", "DL-DE-BY-2.0",
    "GPL-1.0-only", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "LGPL-2.0-only", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later", "GFDL-1.2-only", "GFDL-1.3-only", "0BSD",
    "BSD-1-Clause", "BSD-4-Clause", "MIT-0", "X11", "Apache-1.1", "MPL-1.1", "CDDL-1.0",
    "EPL-1.0",
]


def fetch(url: str, dest: Path) -> bytes:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r:
            dest.write_bytes(r.read())
    return dest.read_bytes()


def main(dl: Path) -> None:
    listing = json.loads(fetch(f"{BASE}/json/licenses.json", dl / "licenses.json"))
    by_id = {x["licenseId"]: x for x in listing["licenses"]}
    wanted = set(EXTRA)
    with open(HF_TABLE, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["kind"] == "spdx":
                wanted.add(row["spdx"])
    licences = {}
    for lid in sorted(wanted):
        meta = by_id[lid]
        if meta.get("isDeprecatedLicenseId"):
            continue  # the -only / -or-later successors in EXTRA carry the text
        text = fetch(f"{BASE}/text/{lid}.txt", dl / "text" / f"{lid}.txt").decode("utf-8")
        licences[lid] = {
            "name": meta["name"],
            "osi": bool(meta.get("isOsiApproved")),
            "fsf": bool(meta.get("isFsfLibre")),
            "see_also": meta.get("seeAlso", []),
            "text": text,
        }
    # deprecated ids keep their flags (for properties) but no text
    deprecated = {lid: {"name": m["name"], "osi": bool(m.get("isOsiApproved")),
                        "fsf": bool(m.get("isFsfLibre")), "see_also": m.get("seeAlso", [])}
                  for lid, m in by_id.items() if m.get("isDeprecatedLicenseId")}
    # every id on the list, with flags only, so the card check can tell SPDX ids apart
    flags = {lid: [int(bool(m.get("isOsiApproved"))), int(bool(m.get("isFsfLibre"))),
                   int(bool(m.get("isDeprecatedLicenseId")))] for lid, m in by_id.items()}
    out = {
        "source": f"https://github.com/spdx/license-list-data/tree/{TAG}",
        "list_version": listing["licenseListVersion"],
        "release_date": listing["releaseDate"],
        "licences": licences,
        "deprecated": deprecated,
        "all_ids": flags,
    }
    data = json.dumps(out, ensure_ascii=False, sort_keys=True).encode("utf-8")
    OUT.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
    print(f"{len(licences)} texts, {len(flags)} ids, list {listing['licenseListVersion']}, "
          f"{OUT.stat().st_size:,} bytes -> {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
