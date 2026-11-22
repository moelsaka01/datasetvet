"""Markdown report and --fail-on (PLAN.md tasks 5.1, 5.3 and the GitHub Action)."""

import json
import re

from test_smoke import fake_imdb, offline_http

from datasetvet.cli import EXIT_FINDINGS, EXIT_OK, findings, main
from datasetvet.config import Settings
from datasetvet.model import BANNED_PHRASES, CheckResult, Evidence, Fact, Family, Report
from datasetvet.pipeline import run_check
from datasetvet.report.markdown import esc, to_markdown

BANNED = re.compile(r"\b(" + "|".join(re.escape(p) for p in BANNED_PHRASES) + r")\b", re.IGNORECASE)


def imdb_report(router) -> Report:
    fake_imdb(router)
    return run_check("hf:stanfordnlp/imdb", Settings(use_cache=False), http=offline_http(router))


def test_markdown_has_the_sections_and_the_footer(router):
    md = to_markdown(imdb_report(router))
    assert md.startswith("# datasetvet: huggingface:stanfordnlp/imdb @ ")
    for title in ("## Card", "## Licence consistency", "## Links", "## Data health"):
        assert title in md
    assert "**Full scan**" in md
    assert "Facts only, not legal advice." in md
    assert "| section | results | statuses |" in md


def test_markdown_has_no_banned_phrase(router):
    md = to_markdown(imdb_report(router))
    assert not BANNED.search(md), BANNED.search(md)


def test_markdown_renders_from_the_json_round_trip(router):
    report = imdb_report(router)
    again = Report.from_dict(json.loads(json.dumps(report.to_dict())))
    assert to_markdown(again) == to_markdown(report)


def test_text_from_a_dataset_cannot_become_markup():
    bs = chr(92)
    assert esc("<script>x</script> [a](b) `c` | d\n e") == (
        f"{bs}<script>x{bs}</script> {bs}[a{bs}](b) {bs}`c{bs}` {bs}| d e")
    assert esc(f"rotten_tomatoes _x_ a{bs}b") == f"rotten_tomatoes {bs}_x{bs}_ a{bs}{bs}b"
    r = CheckResult("health.pii", Family.HEALTH, "found", "PII <b>",
                    [Fact("value <img src=x onerror=1> in a|b", [Evidence(url="javascript:alert(1)")])])
    report = Report.from_dict({
        "dataset": {"hub": "huggingface", "id": "o/d", "revision": "a" * 40, "requested": "x",
                    "requested_revision": None, "url": "https://huggingface.co/datasets/o/d"},
        "tool_version": "0", "created_at": "now", "scanner": "builtin",
        "results": [r.__dict__ | {"family": "health", "facts": [
            {"text": r.facts[0].text, "evidence": [{"url": "javascript:alert(1)"}]}]}]})
    md = to_markdown(report)
    assert not re.search(r"(?<!\\)<", md)  # every "<" is escaped, so no tag can form
    assert "](javascript:" not in md  # only http(s) evidence becomes a link


def test_findings_match_statuses_exactly(router):
    report = imdb_report(router)
    assert findings(report, []) == []
    found = findings(report, ["found"])
    assert found and all(r.status == "found" for r in found)
    assert findings(report, ["restricted"]) == []


def test_cli_writes_markdown_and_fails_on_request(router, tmp_path, monkeypatch):
    from datasetvet import pipeline

    fake_imdb(router)
    real = pipeline.run_check
    monkeypatch.setattr("datasetvet.pipeline.run_check",
                        lambda ref, settings, **kw: real(ref, settings, http=offline_http(router),
                                                          **{k: v for k, v in kw.items()
                                                             if k != "http"}))
    md = tmp_path / "r.md"
    args = ["check", "hf:stanfordnlp/imdb", "--md", str(md), "--no-cache", "-q"]
    assert main(args) == EXIT_OK
    assert md.read_text("utf-8").startswith("# datasetvet:")
    assert main(args + ["--fail-on", "found"]) == EXIT_FINDINGS
    assert main(args + ["--fail-on", "restricted"]) == EXIT_OK
