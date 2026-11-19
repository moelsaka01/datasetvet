"""Banned phrases (PLAN.md task 5.3) in the footer and every rendered terminal report."""

import re

from conftest import hf_fixture
from rich.console import Console
from test_smoke import fake_imdb, offline_http

from datasetvet.config import Settings
from datasetvet.licences.properties import properties
from datasetvet.model import BANNED_PHRASES, FOOTER
from datasetvet.pipeline import run_check
from datasetvet.report.terminal import render

BANNED = re.compile(r"\b(" + "|".join(re.escape(p) for p in BANNED_PHRASES) + r")\b", re.IGNORECASE)


def test_footer_has_no_banned_phrase():
    assert not BANNED.search(FOOTER)
    assert FOOTER.startswith("Facts only, not legal advice.")


def test_properties_have_no_banned_phrase():
    for lid in ("MIT", "CC-BY-NC-ND-4.0", "CC0-1.0", "GPL-3.0-only", "LicenseRef-hf-x"):
        assert not BANNED.search(properties(lid).text())


def _rendered(report) -> str:
    console = Console(record=True, width=200)
    render(report, console)
    return console.export_text()


def test_reports_have_no_banned_phrase(router):
    fake_imdb(router)
    report = run_check("hf:stanfordnlp/imdb", Settings(use_cache=False),
                       http=offline_http(router))
    text = _rendered(report)
    assert "Licence consistency" in text
    assert not BANNED.search(text), BANNED.search(text)


def test_gated_report_has_no_banned_phrase(router):
    import httpx2

    hf_fixture("hle", router, "cais/hle")
    router.add("https://", httpx2.Response(200))
    report = run_check("hf:cais/hle", Settings(use_cache=False), http=offline_http(router))
    assert not BANNED.search(_rendered(report))
