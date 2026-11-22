"""Task 5.9: the warning before a repo with 100,000 or more files is read."""

import re

import pytest
from test_listing import LISTING_CAP, SHA, serve_big_repo, serve_small_files

from datasetvet.checks.health.large import (
    LARGE_REPO_FILES,
    READ_SECONDS_PER_FILE,
    SAMPLED_FLAGS,
    large_repo,
)
from datasetvet.cli import build_parser, can_ask
from datasetvet.config import Settings
from datasetvet.hubs.base import DataPlan, Listing, RepoFile, SplitFile, SplitSource
from datasetvet.model import BANNED_PHRASES
from datasetvet.pipeline import run_check

CARD = ("---\nlicense: mit\nconfigs:\n- config_name: default\n  data_files:\n"
        "  - split: train\n    path: data/part-10002[0-9].parquet\n---\n")
BANNED = re.compile(r"\b(" + "|".join(re.escape(p) for p in BANNED_PHRASES) + r")\b", re.IGNORECASE)


def settings(**kw) -> Settings:
    base = {"check_licences": False, "check_links": False, "use_cache": False,
            "git_fetch": False, "max_scan_bytes": 10**9}
    return Settings(**{**base, **kw})


def data_fetches(router) -> list[str]:
    return [str(r.url) for r in router.calls if f"/resolve/{SHA}/data/" in str(r.url)]


def test_warning_comes_before_any_data_file_is_fetched(router, make_http):
    serve_big_repo(router, LISTING_CAP + 543, readme=CARD)  # 100,543 data files + README
    serve_small_files(router)
    said: list[str] = []
    asked: list[str] = []

    def confirm(text: str) -> bool:
        asked.append(text)
        assert data_fetches(router) == []  # nothing fetched yet when the question is asked
        return True

    report = run_check(f"hf:o/big@{SHA}", settings(), http=make_http(router),
                       progress=said.append, confirm=confirm)
    warning = next(m for m in said if m.startswith("Large repo:"))
    assert "100,544 files" in warning and warning in asked
    assert "--max-scan-bytes" in warning and "--sample-rows" in warning
    assert report.scan.kind == "full" and report.scan.rows_scanned == 30
    assert report.scan.large_repo == "large repo: 100,544 files"
    assert report.scan.header() == "Full scan (large repo: 100,544 files)"
    assert report.scan.large_repo_warning == warning
    assert data_fetches(router)  # and then it did read


def test_declining_skips_only_the_data_scan(router, make_http):
    serve_big_repo(router, LISTING_CAP + 543, readme=CARD)
    serve_small_files(router)
    report = run_check(f"hf:o/big@{SHA}", settings(check_links=True), http=make_http(router),
                       confirm=lambda _t: False)
    assert data_fetches(router) == []
    assert report.scan.kind == "not checked" and "large-repo warning" in report.scan.reason
    assert report.scan.large_repo_warning and "100,544" in report.scan.large_repo_warning
    assert any("data health" in n and "large-repo warning" in n for n in report.not_checked)
    assert report.by_family("card")  # the other checks still ran


def test_without_a_confirm_callback_it_proceeds_and_still_says_so(router, make_http):
    serve_big_repo(router, LISTING_CAP + 543, readme=CARD)
    serve_small_files(router)
    said: list[str] = []
    report = run_check(f"hf:o/big@{SHA}", settings(), http=make_http(router),
                       progress=said.append)
    assert any(m.startswith("Large repo:") for m in said)
    assert report.scan.kind == "full" and report.scan.large_repo_warning


def test_a_cut_off_listing_says_at_least(router, make_http):
    serve_big_repo(router, LISTING_CAP + 5000, fail_page=1,
                   readme=CARD.replace("10002[0-9]", "00001[0-9]"))  # files inside the cut-off
    serve_small_files(router)
    report = run_check(f"hf:o/big@{SHA}", settings(), http=make_http(router))
    assert report.scan.large_repo == f"large repo: at least {LISTING_CAP:,} files"
    assert "Partial scan" in report.scan.header()


def test_a_repo_under_the_limit_gets_no_warning(router, make_http):
    serve_big_repo(router, LISTING_CAP - 2,
                   readme=CARD.replace("10002[0-9]", "00001[0-9]"))  # 99,999 files with README
    serve_small_files(router)
    said: list[str] = []
    report = run_check(f"hf:o/big@{SHA}", settings(), http=make_http(router),
                       progress=said.append, confirm=lambda _t: pytest.fail("asked"))
    assert not any(m.startswith("Large repo:") for m in said)
    assert report.scan.large_repo is None and report.scan.large_repo_warning is None
    assert "large repo" not in report.scan.header()


def test_the_warning_is_not_asked_for_with_no_data(router, make_http):
    serve_big_repo(router, LISTING_CAP + 543, readme=CARD)
    report = run_check(f"hf:o/big@{SHA}", settings(check_data=False), http=make_http(router),
                       confirm=lambda _t: pytest.fail("asked"))
    assert report.scan.large_repo is None


def plan(n_files: int, *, rows: int | None = 1000, size: int = 1_000_000) -> DataPlan:
    files = [SplitFile(f"https://x/{i}", f"d/{i}.parquet", size, "parquet")
             for i in range(n_files)]
    return DataPlan([SplitSource("default", "train", files, rows, n_files * size, "original files",
                                 None)])


def listing(n: int, complete: bool = True) -> Listing:
    return Listing([RepoFile(f"f{i}") for i in range(n)], complete)


def test_estimate_for_a_full_read_uses_the_measured_rate():
    big = large_repo(listing(389_052), plan(146_744, rows=None), settings(max_scan_bytes=10**12))
    assert big and big.kind == "full" and big.data_files == 146_744
    assert big.seconds == pytest.approx(146_744 * READ_SECONDS_PER_FILE)
    text = big.text()
    assert "389,052 files" in text and "146,744 of them data files" in text
    assert "85 minutes" in text and SAMPLED_FLAGS in text


def test_a_sampled_run_estimates_only_the_files_the_sample_needs():
    # 100,000 files of 10 rows each = 1,000,000 rows; a 10,000-row sample needs ~1,000 files
    s = settings(max_scan_bytes=1, sample_rows=10_000)
    big = large_repo(listing(120_000), plan(100_000, rows=1_000_000), s)
    assert big and big.kind == "sampled"
    assert big.seconds == pytest.approx(1_000 * READ_SECONDS_PER_FILE)
    assert "sampled scan" in big.text() and SAMPLED_FLAGS not in big.text()


def test_nothing_to_warn_about_without_data():
    assert large_repo(listing(LARGE_REPO_FILES), DataPlan([], not_checked="gated"),
                      settings()) is None
    assert large_repo(listing(LARGE_REPO_FILES - 1), plan(10), settings()) is None


def test_warning_text_has_no_banned_phrase():
    for p in (plan(146_744, rows=None), plan(5, rows=None)):
        big = large_repo(listing(389_052, complete=False), p, settings())
        assert big and not BANNED.search(big.text()) and "at least 389,052" in big.text()


@pytest.mark.parametrize("flags,env,tty,expected", [
    ([], {}, True, True),
    (["--yes"], {}, True, False),
    (["-y"], {}, True, False),
    ([], {"CI": "true"}, True, False),
    ([], {"GITHUB_ACTIONS": "true"}, True, False),
    ([], {}, False, False),
])
def test_when_the_cli_asks(monkeypatch, flags, env, tty, expected):
    import sys

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: tty, raising=False)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: tty, raising=False)
    args = build_parser().parse_args(["check", "hf:o/d", *flags])
    assert can_ask(args) is expected
