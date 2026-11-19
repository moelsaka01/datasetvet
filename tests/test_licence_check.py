"""Tasks 3.5-3.7: the comparison rule, source resolvers, provenance."""

import httpx2
from spdx_texts import TEXTS, needs_texts

from datasetvet.checks.licence import (
    CardLicence,
    OtherSide,
    _only_placeholder,
    card_licence,
    compare,
    outcome_result,
    sides_from_read,
    source_targets,
)
from datasetvet.checks.provenance import HfParent, ProvenanceContext, check_provenance
from datasetvet.hubs.base import LinkRef, ParentRef, SourceRead, TextBlob
from datasetvet.hubs.github import GitHubResolver, parse_repo
from datasetvet.hubs.huggingface import parent_refs
from datasetvet.hubs.web import WebResolver, html_to_text
from datasetvet.licences.matcher import Detection
from datasetvet.licences.scanner import BuiltinScanner
from datasetvet.model import DatasetRef, Evidence, Family

EV = Evidence(url="https://huggingface.co/datasets/o/d/blob/abc/README.md#L3", revision="abc",
              path="README.md", lines=[3, 3])
SCANNER = BuiltinScanner()
SHA = "9b1e0d4c" + "0" * 32


def c1(value, **extra):
    meta = {"license": value, **extra}
    return card_licence(meta, EV, "README.md@3f2a1c9, YAML line 3")


def side(*exprs, state="read", note="", mentions=True, where="LICENSE@9b1e0d4"):
    dets = [Detection(e, "full text", 100.0, (1, 12)) for e in exprs]
    return OtherSide("LICENSE", where, Evidence(url="https://x/LICENSE"), state, dets,
                     mentions_licence=mentions, note=note)


def test_consistent_sentence_matches_plan_format():
    out = compare(c1("mit"), side("MIT"))
    assert out.status == "consistent"
    assert out.sentence == ("Card says mit (SPDX MIT) (README.md@3f2a1c9, YAML line 3); "
                            "LICENSE@9b1e0d4 says MIT (full text, score 100, lines 1-12); "
                            "these are the same licence.")


def test_inconsistent_differs():
    out = compare(c1("mit"), side("CC-BY-NC-4.0"))
    assert out.status == "inconsistent" and out.sub == "differs"
    assert out.sentence.endswith("says CC-BY-NC-4.0 (full text, score 100, lines 1-12); "
                                 "these differ.")


def test_inconsistent_subset():
    out = compare(c1("mit"), side("MIT AND CC-BY-4.0"))
    assert out.status == "inconsistent" and out.sub == "subset"
    assert "one is part of the other (MIT is part of MIT AND CC-BY-4.0)" in out.sentence


def test_missing_card_side_and_other_side():
    assert compare(c1(None), side("MIT")).status == "missing"
    assert compare(c1("unknown"), side("MIT")).sub == "card missing"
    out = compare(c1("mit"), side(state="no statement", mentions=False))
    assert out.status == "missing" and "has no licence statement" in out.sentence


def test_unknown_cases():
    assert compare(c1("mit"), side(state="unreadable", note="HTTP 401")).sub == "unreadable"
    assert compare(c1("bsd"), side("MIT")).sub == "card unclear"  # family id
    assert compare(c1("other", license_name="my-licence"), side("MIT")).sub == "card unclear"
    assert compare(c1("Apache 2.0"), side("Apache-2.0")).sub == "card unclear"  # not an id
    several = compare(c1("cc-by-4.0"), side("MIT", "Apache-2.0"))
    assert several.status == "unknown" and several.sub == "several licences"
    assert "None of these is the card's licence." in several.extra
    vl = OtherSide("README", "README.md@abc", None, "read",
                   [Detection("CC-BY-SA", "name", None, (5, 5), versionless=True)])
    assert compare(c1("cc-by-sa-4.0"), vl).sub == "versionless"
    assert compare(c1("mit"), side(mentions=True)).sub == "not identified"
    assert compare(c1("llama2"), side("MIT")).sub == "non-SPDX"


def test_card_list_matches_several_detections_as_a_set():
    out = compare(c1(["mit", "cc-by-4.0"]), side("CC-BY-4.0", "MIT"))
    assert out.status == "consistent" and out.sub == "same set"


def test_identical_texts_count_as_either_id():
    d = Detection("GPL-2.0-only", "full text", 100.0, (1, 300), alternatives=["GPL-2.0-or-later"])
    o = OtherSide("COPYING", "COPYING@abc", None, "read", [d])
    out = compare(c1("GPL-2.0-or-later"), o)
    assert out.status == "consistent" and "this text alone does not say which" in out.extra[0]


def test_result_has_both_evidences_and_other_side_properties():
    o = side("CC-BY-NC-4.0")
    r = outcome_result("licence.file:LICENSE", "Card vs LICENSE", Family.LICENCE, c1("mit"), o,
                       compare(c1("mit"), o))
    assert r.status == "inconsistent"
    assert r.facts[0].evidence[0].url.endswith("#L3")
    assert any("NC (NonCommercial)" in f.text for f in r.facts)
    assert not any(f.text.startswith("Properties: MIT") for f in r.facts)


def test_readme_placeholder_section_is_no_statement():
    body = ("- [Licensing Information](#licensing-information)\n\n### Licensing Information\n\n"
            "[More Information Needed](https://github.com/huggingface/datasets/blob/master/"
            "CONTRIBUTING.md#how-to-contribute-to-the-dataset-cards)\n\n### Citation\n")
    assert _only_placeholder(body)
    assert not _only_placeholder(body + "\nSee the license of the source.\n")


def test_source_targets_skip_template_parents_and_duplicates():
    ds = DatasetRef("huggingface", "o/d", "abc", "hf:o/d")
    links = [
        LinkRef("https://github.com/huggingface/datasets/blob/master/CONTRIBUTING.md#x",
                "Repository", True),
        LinkRef("https://github.com/org/repo", "Repository", True),
        LinkRef("https://github.com/org/repo/tree/main/data", "Homepage", True),
        LinkRef("https://huggingface.co/datasets/o/d", "Homepage", True),
        LinkRef("https://huggingface.co/datasets/a/parent", "source_datasets", True),
        LinkRef("https://creativecommons.org/licenses/by/4.0/", "license_link", False),
        LinkRef("https://example.com/unstated", "metadata: x", False),
    ]
    assert [ln.url for ln in source_targets(links, ds)] == [
        "https://github.com/org/repo", "https://creativecommons.org/licenses/by/4.0/"]


# -- resolvers ---------------------------------------------------------------------------------

def refs_body(sha):
    head = f"{sha} HEAD\x00multi_ack symref=HEAD:refs/heads/main\n".encode()
    return b"001e# service=git-upload-pack\n0000" + b"%04x" % (len(head) + 4) + head


def test_parse_repo():
    assert parse_repo("https://github.com/org/repo/tree/main/x") == ("org", "repo")
    assert parse_repo("https://github.com/org/repo.git") == ("org", "repo")
    assert parse_repo("https://github.com/orgs/foo") is None
    assert parse_repo("https://gitlab.com/org/repo") is None


@needs_texts
def test_github_anonymous_makes_no_api_calls(router, make_http):
    router.add("https://github.com/org/repo.git/info/refs",
               httpx2.Response(200, content=refs_body(SHA)))
    mit = TEXTS["MIT"]
    router.add(f"https://raw.githubusercontent.com/org/repo/{SHA}/LICENSE.md",
               httpx2.Response(200, text=mit))
    read = GitHubResolver(make_http(router), token="").read("https://github.com/org/repo")
    assert read.state == "read" and read.revision == SHA
    assert [t.path for t in read.texts] == ["LICENSE.md"]
    assert read.texts[0].evidence.url == f"https://github.com/org/repo/blob/{SHA}/LICENSE.md"
    assert not any("api.github.com" in str(c.url) for c in router.calls)
    sides = sides_from_read(read, SCANNER)
    assert compare(c1("mit"), sides[0]).status == "consistent"


def test_github_no_licence_file_is_unknown_without_token(router, make_http):
    router.add("https://github.com/org/repo.git/info/refs",
               httpx2.Response(200, content=refs_body(SHA)))
    read = GitHubResolver(make_http(router), token="").read("https://github.com/org/repo")
    assert read.state == "no licence file" and "without GITHUB_TOKEN" in read.note
    out = compare(c1("mit"), sides_from_read(read, SCANNER)[0])
    assert out.status == "unknown" and "LICENSE, LICENSE.md" in out.sentence


def test_github_token_path_is_labelled_and_confirms_none(router, make_http):
    router.add("https://github.com/org/repo.git/info/refs",
               httpx2.Response(200, content=refs_body(SHA)))
    router.add("https://api.github.com/repos/org/repo/license", httpx2.Response(404))
    read = GitHubResolver(make_http(router), token="t0k").read("https://github.com/org/repo")
    api = [c for c in router.calls if "api.github.com" in str(c.url)]
    assert api and api[0].headers["authorization"] == "Bearer t0k"
    assert not any("authorization" in c.headers for c in router.calls
                   if "api.github.com" not in str(c.url))
    assert read.confirmed_none
    assert compare(c1("mit"), sides_from_read(read, SCANNER)[0]).status == "missing"


@needs_texts
def test_github_detection_disagreeing_with_ours_is_unknown(router, make_http):
    router.add("https://github.com/org/repo.git/info/refs",
               httpx2.Response(200, content=refs_body(SHA)))
    mit = TEXTS["MIT"]
    router.add(f"https://raw.githubusercontent.com/org/repo/{SHA}/LICENSE",
               httpx2.Response(200, text=mit))
    router.json("https://api.github.com/repos/org/repo/license",
                {"license": {"spdx_id": "Apache-2.0"}, "path": "LICENSE",
                 "html_url": "https://github.com/org/repo/blob/main/LICENSE"})
    read = GitHubResolver(make_http(router), token="t").read("https://github.com/org/repo")
    s = sides_from_read(read, SCANNER)[0]
    assert "disagree" in s.note and compare(c1("mit"), s).status == "unknown"
    assert read.claims[0].source == "GitHub's detection (licensee)"


def test_github_missing_repo_is_unreadable(router, make_http):
    router.add("https://github.com/org/gone.git/info/refs", httpx2.Response(401))
    read = GitHubResolver(make_http(router), token="").read("https://github.com/org/gone")
    assert read.state == "unreadable" and "not found or private" in read.note


def test_web_licence_url_is_not_fetched(router, make_http):
    read = WebResolver(make_http(router)).read("https://creativecommons.org/licenses/by/4.0/")
    assert read.kind == "licence URL" and read.claims[0].raw == "CC-BY-4.0"
    assert router.calls == []
    assert compare(c1("cc-by-4.0"), sides_from_read(read, SCANNER)[0]).status == "consistent"


def test_web_non_licence_page_is_skipped_and_terms_page_is_read(router, make_http):
    web = WebResolver(make_http(router))
    assert web.read("https://example.com/about").state == "skipped"
    router.add("https://example.com/terms", httpx2.Response(
        200, headers={"content-type": "text/html"},
        text="<html><head><title>x</title></head><body><h1>Terms</h1><p>The data is "
             "licensed under CC BY-NC 4.0.</p><script>var a=1</script></body></html>"))
    read = web.read("https://example.com/terms")
    assert read.state == "read" and "var a" not in read.texts[0].text
    assert compare(c1("cc-by-nc-4.0"), sides_from_read(read, SCANNER)[0]).status == \
        "consistent"


def test_html_to_text():
    assert html_to_text("<p>a<b>b</b></p><div>c</div>") == "ab\nc"


# -- provenance --------------------------------------------------------------------------------

def test_parent_refs():
    refs = parent_refs(["original", "extended|squad", "extended|other-wiki", "org/ds",
                        "https://github.com/org/repo", "some free text"])
    assert [(r.hub, r.id, r.url) for r in refs] == [
        ("huggingface", "squad", None), (None, None, None), ("huggingface", "org/ds", None),
        (None, None, "https://github.com/org/repo"), (None, None, None)]
    assert parent_refs("original") == []


def _parent(pid, lic, parents=()):
    ev = Evidence(url=f"https://huggingface.co/datasets/{pid}/blob/s/README.md")
    return HfParent(pid, "s" * 40, card_licence({"license": lic}, ev, f"{pid} README.md@sss",
                                                owner=f"{pid}'s card"),
                    [ParentRef(raw=p, hub="huggingface", id=p) for p in parents])


def _ctx(child_lic, parents, graph, depth=2):
    return ProvenanceContext(
        "me/child", c1(child_lic), [ParentRef(raw=p, hub="huggingface", id=p) for p in parents],
        lambda pid: (graph[pid], "") if pid in graph else (None, "not found"), [], SCANNER,
        depth=depth)


def test_parent_licence_mismatch():
    graph = {"org/parent": _parent("org/parent", "cc-by-sa-4.0")}
    res, _nc = check_provenance(_ctx("mit", ["org/parent"], graph))
    assert [r.status for r in res] == ["inconsistent"]
    assert "org/parent's card says cc-by-sa-4.0" in res[0].facts[0].text
    assert any("SA (ShareAlike)" in f.text for f in res[0].facts)


def test_cycle_terminates():
    graph = {"a/one": _parent("a/one", "mit", ["a/two"]),
             "a/two": _parent("a/two", "mit", ["a/one"])}
    res, _nc = check_provenance(_ctx("mit", ["a/one"], graph, depth=5))
    assert [r.status for r in res] == ["consistent", "consistent", "unknown"]
    assert res[-1].data.get("cycle")


def test_depth_limit_and_unresolvable_parent():
    graph = {"a/one": _parent("a/one", "mit", ["a/two"]), "a/two": _parent("a/two", "mit")}
    res, nc = check_provenance(_ctx("mit", ["a/one", "zz/missing"], graph, depth=1))
    assert [r.status for r in res] == ["consistent", "unknown"]
    assert any("beyond depth 1" in n for n in nc)


@needs_texts
def test_url_parent_through_a_resolver():
    class FakeGitHub:
        def matches(self, url):
            return "github.com" in url

        def read(self, url):
            blob = TextBlob("LICENSE", TEXTS["Apache-2.0"], False,
                            Evidence(url="https://github.com/o/r/blob/s/LICENSE"))
            return SourceRead(url, "github.com/o/r", "github", "read", texts=[blob],
                              revision="s" * 40)

    ctx = ProvenanceContext("me/child", c1("mit"),
                            [ParentRef(raw="https://github.com/o/r",
                                       url="https://github.com/o/r")],
                            lambda _p: (None, ""), [FakeGitHub()], SCANNER)
    res, _ = check_provenance(ctx)
    assert [r.status for r in res] == ["inconsistent"]


def test_card_licence_states():
    assert c1(None).state == "missing" and c1("unknown").state == "missing"
    assert c1("cc").state == "unclear"
    assert c1(["mit", "apache-2.0"]).expression == "MIT AND Apache-2.0"
    assert isinstance(c1("mit"), CardLicence)
