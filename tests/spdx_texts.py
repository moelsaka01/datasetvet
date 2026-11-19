"""Official SPDX licence texts for tests, read from the download cache, never from the repo.

The package ships no licence text (PLAN.md section 4). `python tools/vendor_spdx.py` downloads
the pinned texts to `.datasetvet-cache/spdx/<tag>/text/` (or `DATASETVET_SPDX_DIR`); tests that
need a real licence text use `TEXTS` and are skipped with `needs_texts` when it is absent.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from datasetvet.licences import spdx

ROOT = Path(__file__).resolve().parents[1]
TAG = spdx.spdx_data()["source"].rsplit("/", 1)[-1]
SPDX_DIR = Path(os.environ.get("DATASETVET_SPDX_DIR") or ROOT / ".datasetvet-cache" / "spdx" / TAG)
INDEXED = sorted(spdx.spdx_data()["licences"])  # the ids the fingerprint index covers


def _load() -> dict[str, str]:
    d = SPDX_DIR / "text"
    out = {}
    for lid in INDEXED:
        p = d / f"{lid}.txt"
        if p.exists():
            out[lid] = p.read_text("utf-8")
    return out if len(out) == len(INDEXED) else {}


TEXTS = _load()
needs_texts = pytest.mark.skipif(
    not TEXTS, reason=f"SPDX licence texts not downloaded to {SPDX_DIR}; run "
                      "python tools/vendor_spdx.py")
