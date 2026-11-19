"""Each card rule (PLAN.md 5.1) with a passing and a failing fixture card."""

from datasetvet.checks.card import check_card, check_citation, check_licence_field, check_metadata
from datasetvet.hubs.huggingface import extract_links, parse_card
from datasetvet.model import Evidence

EV = Evidence(url="https://huggingface.co/datasets/o/d/blob/abc/README.md", revision="abc",
              path="README.md")

GOOD = """---
license: cc-by-4.0
pretty_name: Good Set
language:
- en
task_categories:
- text-classification
size_categories:
- 1K<n<10K
source_datasets:
- extended|other/parent
configs:
- config_name: default
  data_files: data/*.parquet
---
# Good Set

- **Homepage:** https://example.org/good
- **Paper:** [arXiv](https://arxiv.org/abs/2101.00001)
- **Point of Contact:** mailto:someone@example.org

## Citation

```bibtex
@inproceedings{good, title={Good}}
```
"""

BAD = """---
license: unknown
size_categories:
- lots
---
Some text without headings.
"""


def card(text, tags=None):
    return parse_card(text, EV, tags or [])


def status(results, check):
    return next(r.status for r in results if r.check == check)


def test_good_card_all_present():
    c = card(GOOD, ["modality:text"])
    results, nc = check_card(c, extract_links(c))
    assert nc == []
    for check in ("card.licence", "card.pretty_name", "card.language", "card.task_categories",
                  "card.size_categories", "card.configs", "card.citation", "card.stated_source"):
        assert status(results, check) == "present", check
    lic = next(r for r in results if r.check == "card.licence")
    assert lic.facts[0].evidence[0].url.endswith("#L2")  # YAML line of `license`


def test_bad_card_missing_and_invalid():
    c = card(BAD)
    results, _ = check_card(c, extract_links(c))
    assert status(results, "card.licence") == "missing"  # `unknown` counts as missing
    assert status(results, "card.pretty_name") == "missing"
    assert status(results, "card.language") == "missing"  # modality unknown -> treated as text
    assert status(results, "card.task_categories") == "missing"
    assert status(results, "card.size_categories") == "invalid"
    assert status(results, "card.configs") == "missing"
    assert status(results, "card.citation") == "missing"
    assert status(results, "card.stated_source") == "missing"


def test_licence_field_variants():
    assert check_licence_field(card("---\nlicense: [mit, apache-2.0]\n---\n")).status == \
        "present"
    assert check_licence_field(card("---\nlicense: ''\n---\n")).status == "missing"
    assert check_licence_field(card("---\npretty_name: x\n---\n")).status == "missing"
    assert check_licence_field(card("---\nlicense: {a: 1}\n---\n")).status == "invalid"
    other = check_licence_field(card("---\nlicense: other\nlicense_name: llama2\n---\n"))
    assert other.status == "present"
    assert "license_name: llama2" in other.facts[1].text


def test_language_not_required_for_image_only():
    names = [r.check for r in check_metadata(card("---\nlicense: mit\n---\n",
                                                  ["modality:image"]))]
    assert "card.language" not in names


def test_pretty_name_falls_back_to_heading():
    r = next(r for r in check_metadata(card("---\nlicense: mit\n---\n\n# My Data\n"))
             if r.check == "card.pretty_name")
    assert r.status == "present" and "My Data" in r.facts[0].text
    assert r.facts[0].evidence[0].lines == [5, 5]


def test_citation_rules():
    assert check_citation(card("## Citation\n\n```\n@misc{x}\n```\n")).status == "present"
    assert check_citation(card("## Citation Information\n\nSee doi 10.1234/abc.5\n")).status \
        == "present"
    assert check_citation(card("## Citation\n\narXiv:2301.12345\n")).status == "present"
    assert check_citation(card("Use this: @article{x, title={y}}\n")).status == "present"
    assert check_citation(card("## Citation\n\n```\n\n```\n\n## Other\n\n")).status == \
        "missing"
    assert check_citation(card("## Citation\n\n[More Information Needed]\n")).status == \
        "missing"


def test_links_extracted_with_labels_and_lines():
    c = card(GOOD)
    links = {ln.url: ln for ln in extract_links(c)}
    assert links["https://example.org/good"].stated
    assert links["https://example.org/good"].label == "Homepage"
    assert links["https://arxiv.org/abs/2101.00001"].evidence.lines == [19, 19]
    assert not any(u.startswith("mailto") for u in links)


def test_license_link_is_a_target_but_not_a_stated_source():
    c = card("---\nlicense: other\nlicense_link: https://example.org/terms\n---\n")
    (ln,) = extract_links(c)
    assert ln.label == "license_link" and not ln.stated
    results, _ = check_card(c, [ln])
    assert status(results, "card.stated_source") == "missing"


def test_unreadable_card_text_is_not_reported_missing():
    from datasetvet.hubs.base import Card

    c = Card(text=None, metadata={"license": "mit"}, body="",
             evidence=Evidence(note="README.md is not readable"))
    results, nc = check_card(c, [])
    assert "card.citation" not in [r.check for r in results]
    assert nc and "citation" in nc[0]


def test_broken_yaml_is_reported():
    c = card("---\nlicense: [mit\n---\n# T\n")
    results, _ = check_card(c, [])
    assert c.yaml_error and status(results, "card.licence") == "missing"
    assert any("does not parse" in f.text for f in results[0].facts)


def test_emoji_citation_heading_without_block_is_missing_with_reason():
    r = check_citation(card("## ✏️ Citation\n\nSee [here](https://x.org/c.txt).\n"))
    assert r.status == "missing" and "citation heading" in r.facts[0].text
    assert check_citation(card("## ✏️ Citation\n\n```\n@misc{x}\n```\n")).status == \
        "present"


def test_labelled_markdown_links_count_as_stated_sources():
    c = card("# T\n\n\U0001F310 [Website](https://lastexam.ai) | [Paper](https://x.ai/paper) | "
             "[Center for X](https://x.org/)\n")
    links = {ln.url: ln for ln in extract_links(c)}
    assert links["https://lastexam.ai"].stated and links["https://lastexam.ai"].label == \
        "Website"
    assert links["https://x.ai/paper"].stated
    assert "https://x.org/" not in links  # an unlabelled link is not a stated source
