"""ScanCode wrapper (task 3.4). Runs only where the [scan] extra is installed (CI job
scan-windows); elsewhere the absence path is tested."""

import pytest
from spdx_texts import TEXTS, needs_texts

from datasetvet.licences.scanner import (
    BuiltinScanner,
    ScanCodeUnavailable,
    get_scanner,
    scancode_available,
)

HAVE = scancode_available()
needs_scancode = pytest.mark.skipif(not HAVE, reason="ScanCode ([scan] extra) not installed")


@pytest.mark.skipif(HAVE, reason="ScanCode is installed")
def test_absent_scancode_is_reported_and_auto_falls_back():
    with pytest.raises(ScanCodeUnavailable, match=r"datasetvet\[scan\]"):
        get_scanner("scancode")
    assert isinstance(get_scanner("auto"), BuiltinScanner)


@needs_scancode
@pytest.mark.parametrize("text,expected", [
    # measured: ScanCode 32.5.0 scores this phrasing 99, but "released under the CC BY-NC 4.0
    # license" only 50 (below SCANCODE_MIN_SCORE); Phase 4 tunes the threshold on the dev split
    ("# Data\n\nLicensed under CC BY-NC 4.0.\n", "CC-BY-NC-4.0"),
    ("## License\nMIT\n", "MIT"),
])
def test_scancode_notices(text, expected):
    found = [d.expression for d in get_scanner("scancode").detect(text)]
    assert expected in found


@needs_scancode
@needs_texts
def test_scancode_licence_file():
    text = TEXTS["Apache-2.0"]
    d = get_scanner("scancode").detect(text)
    assert [x.expression for x in d] == ["Apache-2.0"] and d[0].method == "scancode"
    assert d[0].score >= 90 and d[0].lines
