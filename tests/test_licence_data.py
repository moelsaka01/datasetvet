"""Tasks 3.1-3.3: HF id table, SPDX wrapper, published properties."""

import gzip
import re
import urllib.request

import pytest
from spdx_texts import SPDX_DIR, needs_texts

from datasetvet.licences import hf_ids, spdx
from datasetvet.licences.matcher import _index
from datasetvet.licences.properties import cc_table, properties

TEXTED = {i for lic in _index() for i in lic.ids}


# -- 3.1 HF licence ids ------------------------------------------------------------------------

def test_every_hf_row_is_well_formed():
    rows = hf_ids.table()
    assert len(rows) == 83
    for hf_id, row in rows.items():
        assert row["kind"] in ("spdx", "family", "non-spdx", "special"), hf_id
        assert row["source"].startswith("https://github.com/huggingface/hub-docs/blob/")
        if row["kind"] == "spdx":
            assert spdx.spdx_id(row["spdx"]) == row["spdx"], hf_id
        else:
            assert row["spdx"] == "", hf_id


def test_every_spdx_target_has_a_text_for_the_matcher():
    for row in hf_ids.table().values():
        if row["kind"] != "spdx":
            continue
        sid = row["spdx"]
        deprecated = spdx.flags(sid)[2]
        if deprecated:  # GPL-2.0 -> GPL-2.0-only / -or-later carry the text
            assert any(t.startswith(sid + "-") for t in TEXTED), sid
        else:
            assert sid in TEXTED, sid


def test_lookup():
    assert hf_ids.lookup("cc-by-nc-4.0").spdx == "CC-BY-NC-4.0"
    assert hf_ids.lookup("CC-BY-NC-4.0").kind == "spdx"
    assert hf_ids.lookup("bsd").kind == "family"
    assert hf_ids.lookup("llama2").expression_key == "LicenseRef-hf-llama2"
    assert hf_ids.lookup("ODC-By-1.0").kind == "spdx-not-hf"
    assert hf_ids.lookup("Apache 2.0").kind == "not-hf"


@pytest.mark.network
def test_hf_list_has_no_unmapped_id():
    url = ("https://raw.githubusercontent.com/huggingface/hub-docs/main/docs/hub/"
           "repositories-licenses.md")
    text = urllib.request.urlopen(url, timeout=30).read().decode("utf-8")
    region = text.split("<!-- region licenses -->")[1].split("<!-- endregion -->")[0]
    ids = set(re.findall(r"\|\s*`([^`]+)`\s*\|", region))
    assert ids and ids <= set(hf_ids.table()), sorted(ids - set(hf_ids.table()))


# -- 3.2 SPDX expressions ------------------------------------------------------------------------

def test_relations():
    assert spdx.relation("MIT", "mit").kind == "equivalent"
    assert spdx.relation("GPL-2.0", "GPL-2.0-only").kind == "equivalent"
    assert spdx.relation("GPL-2.0-only", "GPL-2.0-or-later").kind == "differs"
    r = spdx.relation("MIT", "MIT AND CC-BY-4.0")
    assert r.kind == "subset" and "MIT is part of MIT AND CC-BY-4.0" in r.detail
    assert spdx.relation("MIT OR Apache-2.0", "Apache-2.0 OR MIT").kind == "equivalent"
    assert spdx.relation("MIT", "not a licence").kind == "unparsed"


def test_licence_refs_parse_but_unknown_ids_do_not():
    assert spdx.normalise("LicenseRef-hf-llama2") == "LicenseRef-hf-llama2"
    assert spdx.parse("llama2") is None
    assert spdx.spdx_id("cc-by-sa-4.0") == "CC-BY-SA-4.0"


def test_vendored_list_is_pinned():
    data = spdx.spdx_data()
    assert data["list_version"] == "3.29.0"
    assert data["source"].endswith("/tree/v3.29.0")
    assert len(data["all_ids"]) > 700


# -- 3.3 properties -----------------------------------------------------------------------------

def test_every_cc_licence_on_hfs_list_has_elements_and_a_deed():
    for row in hf_ids.table().values():
        if row["kind"] == "spdx" and row["spdx"].startswith(("CC-BY", "CC0")):
            els, deed = cc_table()[row["spdx"]]
            assert deed.startswith("https://creativecommons.org/"), row["spdx"]
            assert row["spdx"] == "CC0-1.0" or "BY" in els


def test_properties_text():
    p = properties("CC-BY-NC-SA-4.0")
    assert p.cc_elements == ["BY", "NC", "SA"]
    assert "NC (NonCommercial)" in p.text() and "SA (ShareAlike)" in p.text()
    mit = properties("MIT")
    assert mit.cc_elements == [] and mit.cc_deed is None and mit.osi
    assert "not on the SPDX list" in properties("LicenseRef-hf-llama2").text()
    assert properties("GPL-2.0").deprecated


def test_no_other_property_is_emitted():
    text = " ".join(properties(i).text() for i in ("MIT", "CC-BY-NC-4.0", "GPL-3.0-only",
                                                   "CC0-1.0", "ODbL-1.0"))
    for word in ("commercial use", "permissive", "copyleft", "allowed", "safe", "free to"):
        assert word not in text.lower()


# -- shipped SPDX data: derived only, no licence text ------------------------------------------

def _shipped(name):
    import gzip
    from importlib import resources
    return gzip.decompress(resources.files("datasetvet.data").joinpath(name).read_bytes())


def test_shipped_spdx_data_holds_no_licence_text():
    for name in ("spdx_licences.json.gz", "spdx_fingerprints.json.gz"):
        raw = _shipped(name).decode("utf-8")
        assert '"text"' not in raw, name
        for phrase in ("hereby granted", "WITHOUT WARRANTY", "Creative Commons Corporation",
                       "Everyone is permitted to copy", "Redistribution and use"):
            assert phrase not in raw, (name, phrase)


def test_fingerprint_index_covers_the_listed_licences():
    from datasetvet.licences import matcher

    fp = matcher.fingerprints()
    assert fp["list_version"] == spdx.list_version()
    assert TEXTED == set(spdx.spdx_data()["licences"])
    assert len(fp["groups"]) == len(_index()) == 87


def test_varint_roundtrip():
    from datasetvet.licences import matcher

    nums = [0, 1, 127, 128, 300, 2**40, 0, 5]
    assert matcher._unvarints(matcher._varints(nums)) == nums


@needs_texts
def test_shipped_index_is_rebuilt_exactly_from_the_official_texts():
    import importlib.util
    from pathlib import Path

    tool = Path(__file__).resolve().parents[1] / "tools" / "vendor_spdx.py"
    spec = importlib.util.spec_from_file_location("vendor_spdx", tool)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    meta_bytes, fp_bytes, _ = mod.build(SPDX_DIR)
    # the JSON inside must match byte for byte; the gzip stream depends on the zlib build
    assert gzip.decompress(meta_bytes) == gzip.decompress(mod.META_OUT.read_bytes())
    assert gzip.decompress(fp_bytes) == gzip.decompress(mod.FP_OUT.read_bytes())
