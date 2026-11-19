"""Build the SPDX data the package ships, from the official SPDX source (PLAN.md section 4).

Usage:
    python tools/vendor_spdx.py            download (if needed) and rewrite both data files
    python tools/vendor_spdx.py --check    rebuild in memory; exit 1 if the shipped files differ
    python tools/vendor_spdx.py --dir D    keep the downloaded SPDX files in D

It downloads `json/licenses.json` and `text/<id>.txt` from github.com/spdx/license-list-data at
TAG into the download directory (default `.datasetvet-cache/spdx/<TAG>`, git-ignored), then
writes:

- `src/datasetvet/data/spdx_licences.json.gz`: list metadata only (ids, names, OSI / FSF /
  deprecated flags, `seeAlso` URLs). **No licence text.**
- `src/datasetvet/data/spdx_fingerprints.json.gz`: the built-in matcher's fingerprint index
  (`matcher.build_fingerprints`): per licence, hashed word bigrams and their counts. **No
  licence text**; the words cannot be read back from it.

The licence texts themselves stay in the download directory and are never committed or
packaged. The offline tests that need them (`spdx_texts` marker) read the same directory and
are skipped when it is absent; `--check` proves the shipped index is reproducible.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import time
import urllib.request
from pathlib import Path

TAG = "v3.29.0"
BASE = f"https://raw.githubusercontent.com/spdx/license-list-data/{TAG}"
SOURCE = f"https://github.com/spdx/license-list-data/tree/{TAG}"
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "datasetvet" / "data"
META_OUT = DATA / "spdx_licences.json.gz"
FP_OUT = DATA / "spdx_fingerprints.json.gz"
HF_TABLE = DATA / "hf_licence_ids.csv"
DEFAULT_DIR = ROOT / ".datasetvet-cache" / "spdx" / TAG

sys.path.insert(0, str(ROOT / "src"))
from datasetvet.licences.matcher import build_fingerprints, fingerprint_bytes

# Licences in the matcher beyond the ones HF's id list maps to: other versions of the same
# families, and licences seen on data repos. The deprecated HF targets (GPL-2.0 ...) are
# replaced by their -only / -or-later successors.
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
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    body = r.read()
                break
            except OSError:  # connection resets happen; retry with backoff
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(body)
        tmp.replace(dest)
    return dest.read_bytes()


def wanted_ids() -> set[str]:
    wanted = set(EXTRA)
    with open(HF_TABLE, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["kind"] == "spdx":
                wanted.add(row["spdx"])
    return wanted


def load_texts(dl: Path) -> tuple[dict, dict[str, str]]:
    """(licenses.json, {id: official text}) for every licence the matcher indexes."""
    listing = json.loads(fetch(f"{BASE}/json/licenses.json", dl / "licenses.json"))
    by_id = {x["licenseId"]: x for x in listing["licenses"]}
    texts = {}
    for lid in sorted(wanted_ids()):
        if by_id[lid].get("isDeprecatedLicenseId"):
            continue  # the -only / -or-later successors in EXTRA carry the text
        texts[lid] = fetch(f"{BASE}/text/{lid}.txt", dl / "text" / f"{lid}.txt").decode("utf-8")
    return listing, texts


def build(dl: Path) -> tuple[bytes, bytes, str]:
    listing, texts = load_texts(dl)
    by_id = {x["licenseId"]: x for x in listing["licenses"]}

    def meta(m: dict) -> dict:
        return {"name": m["name"], "osi": bool(m.get("isOsiApproved")),
                "fsf": bool(m.get("isFsfLibre")), "see_also": m.get("seeAlso", [])}

    out = {
        "source": SOURCE,
        "list_version": listing["licenseListVersion"],
        "release_date": listing["releaseDate"],
        "note": ("SPDX licence list metadata only (ids, names, flags, seeAlso URLs). No licence "
                 "text is shipped; the matcher uses spdx_fingerprints.json.gz."),
        "licences": {lid: meta(by_id[lid]) for lid in texts},  # the ids the matcher indexes
        "deprecated": {lid: meta(m) for lid, m in by_id.items()
                       if m.get("isDeprecatedLicenseId")},
        "all_ids": {lid: [int(bool(m.get("isOsiApproved"))), int(bool(m.get("isFsfLibre"))),
                          int(bool(m.get("isDeprecatedLicenseId")))]
                    for lid, m in by_id.items()},
    }
    meta_bytes = gzip.compress(json.dumps(out, ensure_ascii=False, sort_keys=True).encode(),
                               compresslevel=9, mtime=0)
    fp = build_fingerprints(texts, SOURCE, listing["licenseListVersion"])
    summary = (f"{len(texts)} licences in {len(fp['groups'])} fingerprint groups, "
               f"{len(by_id)} ids, list {listing['licenseListVersion']}")
    return meta_bytes, fingerprint_bytes(fp), summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="SPDX download directory")
    ap.add_argument("--check", action="store_true",
                    help="rebuild and compare with the shipped files; write nothing")
    args = ap.parse_args(argv)
    meta_bytes, fp_bytes, summary = build(args.dir)
    if args.check:
        same = META_OUT.read_bytes() == meta_bytes and FP_OUT.read_bytes() == fp_bytes
        print(("identical: " if same else "DIFFERENT: ") + summary)
        return 0 if same else 1
    META_OUT.write_bytes(meta_bytes)
    FP_OUT.write_bytes(fp_bytes)
    print(f"{summary}\n{META_OUT.name}: {len(meta_bytes):,} bytes\n"
          f"{FP_OUT.name}: {len(fp_bytes):,} bytes\nlicence texts kept in {args.dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
