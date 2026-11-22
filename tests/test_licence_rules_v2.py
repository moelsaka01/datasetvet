"""Phase 5.5 rules (PLAN.md 5.2 "Phase 5.5", 8.1): one test (or more) per rule.

1. A source repo's software licence: "the source code licence differs", not a contradiction.
2. Several licences in one text: OSI-approved software licences the card does not name are set
   aside as code licences.
3. One status per dataset (`licence.summary`), with "uncontradicted" when only the card states a
   licence.
"""

import pytest

from datasetvet.checks import licence as lic
from datasetvet.checks.licence import (
    OtherSide,
    card_licence,
    compare,
    outcome_result,
    sides_from_read,
    software_only,
    summarise,
)
from datasetvet.hubs.base import LicenceClaim, SourceRead, TextBlob
from datasetvet.licences.matcher import Detection
from datasetvet.licences.scanner import BuiltinScanner
from datasetvet.model import Evidence, Family

EV = Evidence(url="https://huggingface.co/datasets/o/d/blob/abc/README.md#L3", revision="abc",
              path="README.md", lines=[3, 3])
SHA = "9b1e0d4c" + "0" * 32


def c1(value, **extra):
    return card_licence({"license": value, **extra}, EV, "README.md@3f2a1c9, YAML line 3")


def gh_side(*exprs, path="LICENSE"):
    dets = [Detection(e, "full text", 100.0, (1, 12)) for e in exprs]
    return OtherSide(f"github.com/org/repo {path}", f"github.com/org/repo {path}@9b1e0d4",
                     Evidence(url="https://x"), "read", dets, mentions_licence=True,
                     code_file=not path.upper().startswith("DATA") and "DATA" not in
                     path.upper())


def own_side(*exprs, label="LICENSE", state="read", mentions=True, note=""):
    dets = [Detection(e, "full text", 100.0, (1, 12)) for e in exprs]
    return OtherSide(label, f"{label}@abc1234", Evidence(url="https://y"), state, dets,
                     mentions_licence=mentions, note=note)


def result(check, card, side):
    return outcome_result(check, "Card vs " + side.label, Family.LICENCE, card, side,
                          compare(card, side))


@pytest.fixture(autouse=True)
def rules_on(monkeypatch):
    """The frozen v2 setting (eval/config-v2.yml `frozen`)."""
    for k, v in {"CODE_LICENCE_RULE": True, "SOFTWARE_ASIDE_RULE": True,
                 "UNCONTRADICTED_RULE": True, "CODE_RULE_NEEDS_DATA_CARD": True}.items():
        monkeypatch.setattr(lic, k, v)


# -- the OSI flag -----------------------------------------------------------------------------

def test_software_only_uses_the_spdx_osi_flag():
    assert software_only({"MIT"}) and software_only({"Apache-2.0", "BSD-3-Clause"})
    assert software_only({"GPL-2.0-only"})
    assert not software_only({"CC-BY-4.0"}) and not software_only({"CC0-1.0"})
    assert not software_only({"MIT", "CC-BY-4.0"})
    assert not software_only(set()) and not software_only({"LicenseRef-hf-llama2"})


# -- rule 1: a source repo's code licence ---------------------------------------------------

def test_source_repo_software_licence_is_not_a_contradiction():
    out = compare(c1("cc-by-sa-4.0"), gh_side("Apache-2.0"))  # hotpot_qa's case
    assert out.status == "unknown" and out.sub == "code licence"
    assert "the source code licence differs" in out.sentence
    assert "Not counted as a contradiction" in out.extra[0]


def test_code_licence_rule_needs_a_data_licence_on_the_card():
    # card Apache-2.0, repo MIT: both software licences -> still a plain difference
    out = compare(c1("apache-2.0"), gh_side("MIT"))
    assert out.status == "inconsistent" and out.sub == "differs"


def test_code_licence_rule_any_card_variant(monkeypatch):
    monkeypatch.setattr(lic, "CODE_RULE_NEEDS_DATA_CARD", False)
    assert compare(c1("apache-2.0"), gh_side("MIT")).sub == "code licence"


def test_a_data_licence_in_a_source_repo_still_differs():
    out = compare(c1("cc-by-3.0"), gh_side("CC0-1.0"))  # wiki_lingua's repo: CC0
    assert out.status == "inconsistent" and out.sub == "differs"


def test_data_licence_file_is_compared_normally():
    out = compare(c1("cc-by-nc-4.0"), gh_side("Apache-2.0", path="DATA_LICENSE"))
    assert out.status == "inconsistent"


def test_same_licence_in_source_repo_stays_consistent():
    assert compare(c1("cc-by-4.0"), gh_side("CC-BY-4.0")).status == "consistent"


def test_own_repo_licence_file_is_not_a_code_licence():
    # the dataset's own LICENSE file is about the dataset: no code-licence rule
    out = compare(c1("cc-by-4.0"), own_side("MIT"))
    assert out.status == "inconsistent"


def test_several_software_licences_in_a_source_repo():
    out = compare(c1("cc-by-4.0"), gh_side("MIT", "Apache-2.0"))
    assert out.status == "unknown" and out.sub == "code licence"


def test_rule_off_restores_v1(monkeypatch):
    monkeypatch.setattr(lic, "CODE_LICENCE_RULE", False)
    assert compare(c1("cc-by-sa-4.0"), gh_side("Apache-2.0")).status == "inconsistent"


def test_sides_from_read_marks_github_licence_files():
    read = SourceRead("https://github.com/org/repo", "github.com/org/repo", "github", "read",
                      texts=[TextBlob("LICENSE", "MIT License\n", False, Evidence(url="u")),
                             TextBlob("DATA_LICENSE", "x", False, Evidence(url="v"))],
                      revision=SHA)
    a, b = sides_from_read(read, BuiltinScanner())
    assert a.code_file and not b.code_file
    web = SourceRead("https://e.org/license", "e.org/license", "web page", "read",
                     texts=[TextBlob("license", "MIT", False, Evidence(url="w"))])
    assert not sides_from_read(web, BuiltinScanner())[0].code_file


def test_github_detection_only_counts_as_a_code_licence():
    read = SourceRead("https://github.com/org/repo", "github.com/org/repo", "github", "read",
                      claims=[LicenceClaim("GitHub's detection (licensee)", "MIT",
                                           Evidence(url="u"))], revision=SHA)
    (s,) = sides_from_read(read, BuiltinScanner())
    assert s.code_file and compare(c1("cc-by-4.0"), s).sub == "code licence"


def test_no_licence_file_found_anonymously_has_its_own_sub():
    read = SourceRead("https://github.com/org/repo", "github.com/org/repo", "github",
                      "no licence file", note="other file names are not checked",
                      revision=SHA)
    (s,) = sides_from_read(read, BuiltinScanner())
    assert compare(c1("mit"), s).sub == "no licence file found"
    read.confirmed_none = True
    (s,) = sides_from_read(read, BuiltinScanner())
    assert compare(c1("mit"), s).status == "missing"


# -- rule 2: software licences set aside inside one text ------------------------------------

def test_readme_naming_code_and_data_licences():
    # deepmind/code_contests: README names CC-BY-4.0, MIT and Apache-2.0; card CC-BY-4.0
    out = compare(c1("cc-by-4.0"), own_side("CC-BY-4.0", "MIT", "Apache-2.0",
                                            label="README text"))
    assert out.status == "consistent" and out.sub == "same set, plus software licences"
    assert "Apache-2.0, MIT" in out.extra[0]


def test_set_aside_never_hides_a_second_data_licence():
    out = compare(c1("cc-by-4.0"), own_side("CC-BY-4.0", "CC-BY-SA-4.0", label="README text"))
    assert out.status == "unknown" and out.sub == "several licences"


def test_set_aside_needs_the_cards_licence_in_the_text():
    out = compare(c1("cc-by-4.0"), own_side("CC-BY-SA-4.0", "MIT", label="README text"))
    assert out.status == "unknown"


def test_set_aside_not_for_a_software_licence_card():
    out = compare(c1("mit"), own_side("MIT", "Apache-2.0", label="README text"))
    assert out.status == "unknown" and out.sub == "several licences"


def test_set_aside_rule_off(monkeypatch):
    monkeypatch.setattr(lic, "SOFTWARE_ASIDE_RULE", False)
    out = compare(c1("cc-by-4.0"), own_side("CC-BY-4.0", "MIT", label="README text"))
    assert out.status == "unknown"


# -- rule 3: one status per dataset ---------------------------------------------------------

def summary_of(card, *pairs):
    return summarise(card, [result(check, card, s) for check, s in pairs])


def test_only_the_card_states_a_licence_is_uncontradicted():
    card = c1("mit")
    s = summary_of(card, ("licence.readme", own_side(label="README text", state="no statement",
                                                     mentions=False)))
    assert s.check == "licence.summary" and s.status == "consistent"
    assert s.data["sub"] == "uncontradicted"
    assert "uncontradicted, not confirmed" in s.facts[0].text


def test_uncontradicted_rule_off_gives_unknown(monkeypatch):
    monkeypatch.setattr(lic, "UNCONTRADICTED_RULE", False)
    card = c1("mit")
    s = summary_of(card, ("licence.readme", own_side(label="README text", state="no statement",
                                                     mentions=False)))
    assert s.status == "unknown"


def test_summary_confirmed_and_inconsistent_and_missing():
    card = c1("cc-by-4.0")
    s = summary_of(card, ("licence.readme", own_side("CC-BY-4.0", label="README text")))
    assert s.status == "consistent" and s.data["sub"] == "confirmed"
    s = summary_of(card, ("licence.readme", own_side("CC-BY-4.0", label="README text")),
                   ("licence.file:LICENSE", own_side("MIT")))
    assert s.status == "inconsistent" and "1 of 2 comparisons differ" in s.facts[0].text
    s = summary_of(c1(None), ("licence.readme", own_side("MIT", label="README text")))
    assert s.status == "missing"
    s = summary_of(c1("other"), ("licence.readme", own_side("MIT", label="README text")))
    assert s.status == "unknown" and s.data["sub"] == "card unclear"


def test_code_licence_and_missing_source_file_do_not_block():
    card = c1("cc-by-sa-4.0")
    nofile = OtherSide("github.com/a/b", "github.com/a/b@1234567", None, "read",
                       mentions_licence=True, no_file=True)
    s = summary_of(card,
                   ("licence.readme", own_side(label="README text", state="no statement",
                                               mentions=False)),
                   ("licence.source:github.com/org/repo LICENSE", gh_side("Apache-2.0")),
                   ("licence.source:github.com/a/b", nofile))
    assert s.status == "consistent" and s.data["sub"] == "uncontradicted"
    assert any("source code licence differs" in f.text for f in s.facts)


def test_an_unidentified_licence_text_blocks():
    card = c1("mit")
    s = summary_of(card, ("licence.readme", own_side(label="README text", mentions=True)))
    assert s.status == "unknown" and s.data["sub"] == "unresolved"


def test_own_readme_unreadable_blocks_but_an_unreadable_source_does_not():
    card = c1("mit")
    gated = own_side(label="README text", state="unreadable", note="HTTP 401")
    assert summary_of(card, ("licence.readme", gated)).status == "unknown"
    gone = OtherSide("github.com/x/y", "github.com/x/y", None, "unreadable", note="HTTP 404")
    s = summary_of(card, ("licence.readme", own_side(label="README text",
                                                     state="no statement", mentions=False)),
                   ("licence.source:github.com/x/y", gone))
    assert s.status == "consistent" and s.data["sub"] == "uncontradicted"


def test_several_licences_text_blocks_uncontradicted():
    card = c1("cc-by-4.0")
    s = summary_of(card, ("licence.readme", own_side("CC-BY-SA-4.0", "CC0-1.0",
                                                     label="README text")))
    assert s.status == "unknown"


def test_summary_is_a_licence_family_result():
    from datasetvet.model import LicenceStatus

    card = c1("mit")
    s = summary_of(card, ("licence.readme", own_side("MIT", label="README text")))
    assert s.family == Family.LICENCE and s.status == LicenceStatus.CONSISTENT


def test_summary_names_are_joined_as_a_sentence():
    card = c1("cc-by-nc-4.0")
    s = summary_of(card, ("licence.readme", own_side("CC-BY-NC-4.0", label="README text")),
                   ("licence.file:LICENSE", own_side("CC-BY-NC-4.0")),
                   ("licence.file:DATA", own_side("CC-BY-NC-4.0", label="DATA")))
    assert "confirmed by the README text, LICENSE and DATA, and no comparison differs" in \
        s.facts[0].text
    assert ";" not in s.facts[0].text.split("confirmed by")[1]
