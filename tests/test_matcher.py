"""Built-in licence matcher (PLAN.md section 4): full texts, notices, URLs."""

import pytest

from datasetvet.licences import matcher, spdx
from datasetvet.licences.scanner import BuiltinScanner, get_scanner, scancode_detections

TEXTS = spdx.spdx_data()["licences"]


def exprs(text):
    return [(d.expression, d.method) for d in matcher.detect(text)]


@pytest.mark.parametrize("lid", sorted(TEXTS))
def test_every_vendored_text_identifies_itself(lid):
    dets = matcher.match_full_text(TEXTS[lid]["text"])
    assert len(dets) == 1
    d = dets[0]
    assert d.method == "full text" and d.score >= 99
    assert lid in [d.expression, *d.alternatives]


def test_identical_texts_are_one_group():
    d = matcher.match_full_text(TEXTS["GPL-2.0-or-later"]["text"])[0]
    assert d.expression == "GPL-2.0-only" and d.alternatives == ["GPL-2.0-or-later"]


def test_close_relatives_are_told_apart():
    for lid in ("MIT", "MIT-0", "X11", "ISC", "0BSD", "BSD-2-Clause", "BSD-3-Clause",
                "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0",
                "CC-BY-1.0", "CC-BY-SA-1.0", "GPL-3.0-only", "AGPL-3.0-only"):
        assert matcher.match_full_text(TEXTS[lid]["text"])[0].expression == lid, lid


def test_licence_with_copyright_header_still_matches():
    text = "Copyright (c) 2021 Some Lab\nAll rights reserved.\n\n" + TEXTS["MIT"]["text"]
    assert exprs(text) == [("MIT", "full text")]


def test_readme_containing_a_licence_text():
    prose = "We collected these sentences from public forums and cleaned them by hand. " * 30
    body = (f"# Data\n\n{prose}\n\n## License\n\n"
            + TEXTS["MIT"]["text"] + "\n## Citation\n\n```\n@misc{x}\n```\n")
    dets = matcher.detect(body)
    assert [(d.expression, d.method) for d in dets] == [("MIT", "contains text")]
    assert dets[0].lines[0] >= 7


def test_mit_inside_x11_reports_x11_only():
    body = "Intro line.\n\n" + TEXTS["X11"]["text"] + "\n\nOther words here and there."
    assert [d.expression for d in matcher.detect(body)] == ["X11"]


def test_names_inside_a_licence_text_are_not_separate_statements():
    # the LGPL text names the GNU GPL; that is part of the text
    assert exprs(TEXTS["LGPL-3.0-only"]["text"]) == [("LGPL-3.0-only", "full text")]


@pytest.mark.parametrize("text,expected", [
    ("The dataset is released under the CC BY-NC 4.0 license.", "CC-BY-NC-4.0"),
    ("## License\nMIT", "MIT"),
    ("License: Apache 2.0", "Apache-2.0"),
    ("Licensed under the Apache License, Version 2.0 (the \"License\").", "Apache-2.0"),
    (("This dataset is licensed under Creative Commons Attribution-NonCommercial-ShareAlike 4.0 "
      "International (CC BY-NC-SA 4.0)."), "CC-BY-NC-SA-4.0"),
    ("This program is distributed under GPLv3.", "GPL-3.0"),
    ("License: CC0", "CC0-1.0"),
    ("Data released under ODC-BY.", "ODC-By-1.0"),
    ("### Licensing Information\n\nThe data is CC-BY-SA-3.0.", "CC-BY-SA-3.0"),
    ("| License | cc-by-4.0 |", "CC-BY-4.0"),
])
def test_notices(text, expected):
    assert [d.expression for d in matcher.detect(text)] == [expected]


def test_names_outside_a_licence_context_are_ignored():
    text = ("MIT researchers built this. The JSON format is used. We thank Apache Spark and "
            "the Creative Commons community. Version 2.0 of the tool.")
    assert matcher.detect(text) == []


def test_one_word_names_need_the_word_license_next_to_them():
    assert matcher.detect("Built at MIT in 2019; see the license section for terms.") == []
    assert [d.expression for d in matcher.detect("Released under the MIT license.")] == ["MIT"]


def test_versionless_cc_is_flagged():
    d = matcher.detect("The data is licensed under CC BY-SA.")
    assert len(d) == 1 and d[0].versionless and d[0].expression == "CC-BY-SA"


def test_spdx_identifier_line():
    d = matcher.detect("SPDX-License-Identifier: Apache-2.0 OR MIT")
    assert [(x.expression, x.method) for x in d] == [("Apache-2.0 OR MIT",
                                                      "SPDX-License-Identifier")]


def test_several_licences_are_all_reported():
    d = matcher.detect("Code is under the MIT license; data under the CC-BY-4.0 license.")
    assert sorted(x.expression for x in d) == ["CC-BY-4.0", "MIT"]


@pytest.mark.parametrize("url,lid", [
    ("https://creativecommons.org/licenses/by-nc/4.0/legalcode", "CC-BY-NC-4.0"),
    ("http://creativecommons.org/licenses/by-sa/3.0/", "CC-BY-SA-3.0"),
    ("https://creativecommons.org/licenses/by/3.0/igo/", "CC-BY-3.0-IGO"),
    ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0"),
    ("https://opensource.org/licenses/MIT", "MIT"),
    ("https://www.apache.org/licenses/LICENSE-2.0", "Apache-2.0"),
    ("https://www.gnu.org/licenses/gpl-3.0.html", "GPL-3.0"),
    ("https://opendatacommons.org/licenses/odbl/1-0/", "ODbL-1.0"),
    ("https://spdx.org/licenses/CDLA-Permissive-2.0.html", "CDLA-Permissive-2.0"),
    ("https://example.com/about", None),
    ("https://creativecommons.org/licenses/by/2.0/kr/", None),  # a port not on the SPDX list
])
def test_licence_urls(url, lid):
    assert matcher.licence_for_url(url) == lid


def test_badge_link_and_alt_text_give_one_detection():
    text = ("[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-"
            "lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)")
    assert [d.expression for d in matcher.detect(text)] == ["CC-BY-4.0"]


def test_deterministic():
    text = "## License\n\n" + TEXTS["CC-BY-4.0"]["text"]
    assert matcher.detect(text) == matcher.detect(text)


def test_scanner_choice():
    assert isinstance(get_scanner("builtin"), BuiltinScanner)
    assert get_scanner("auto").name in ("builtin", "scancode")
    with pytest.raises(ValueError):
        get_scanner("nope")


def test_scancode_output_mapping():
    result = {"license_detections": [
        {"license_expression_spdx": "CC-BY-NC-4.0", "matches": [
            {"score": 100.0, "start_line": 3, "end_line": 3, "matched_text": "CC BY-NC 4.0"}]},
        {"license_expression_spdx": "MIT", "matches": [
            {"score": 60.0, "start_line": 9, "end_line": 9, "matched_text": "mit"}]},
    ]}
    d = scancode_detections(result, 90)
    assert [(x.expression, x.method, x.score, x.lines) for x in d] == [
        ("CC-BY-NC-4.0", "scancode", 100.0, (3, 3))]
