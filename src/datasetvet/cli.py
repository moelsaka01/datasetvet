"""Command-line entry point: `datasetvet check <ref>`. Phase 5 adds `badge`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from datasetvet import __version__
from datasetvet.config import Settings, from_env, parse_bytes

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_FINDINGS = 3  # --fail-on matched a result
FAIL_ON = ("inconsistent", "missing", "invalid", "dead", "unreachable", "restricted", "found")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datasetvet",
        description="Before you train on it, check it. Facts only, not legal advice.",
    )
    parser.add_argument("--version", action="version", version=f"datasetvet {__version__}")
    sub = parser.add_subparsers(dest="command")
    c = sub.add_parser("check", help="check a dataset and print a report",
                       description="Check a dataset: card, licence consistency, provenance, "
                                   "links and data health.")
    c.add_argument("ref", help="dataset reference, e.g. hf:stanfordnlp/imdb, "
                              "hf:org/name@revision or https://huggingface.co/datasets/org/name")
    c.add_argument("--json", metavar="PATH", help="also write the JSON report to PATH")
    c.add_argument("--md", metavar="PATH", help="also write a Markdown report to PATH")
    c.add_argument("--fail-on", action="append", dest="fail_on", metavar="STATUS",
                   choices=FAIL_ON, default=[],
                   help="exit with status 3 when any result has this status (repeatable; for CI). "
                        f"One of: {', '.join(FAIL_ON)}. Default: never")
    c.add_argument("--max-scan-bytes", default=None,
                   help="full-scan limit (default 5GB); above it the data is sampled")
    c.add_argument("--sample-rows", type=int, default=None,
                   help="rows to sample above the limit (default 1,000,000)")
    c.add_argument("--max-download-bytes", default=None,
                   help="sampled scans only: stop downloading files beyond this (default none)")
    c.add_argument("--seed", type=int, default=None, help="sampling seed (default 0)")
    c.add_argument("--no-git-fetch", action="store_true",
                   help="download every data file over HTTP, never with one git fetch")
    c.add_argument("--fetch-workers", type=int, default=None,
                   help="data files downloaded at the same time (default 8)")
    c.add_argument("--full", action="store_true", help="scan every row whatever the size")
    c.add_argument("--config", action="append", dest="configs", metavar="NAME",
                   help="only scan this config (repeatable)")
    c.add_argument("--phone-region", metavar="XX",
                   help="also match national phone formats for region XX (e.g. GB, US)")
    c.add_argument("--no-data", action="store_true", help="skip the data-health scan")
    c.add_argument("--no-links", action="store_true", help="skip the link check")
    c.add_argument("--max-links", type=int, default=None, help="link-check limit (default 200)")
    c.add_argument("--scanner", choices=["auto", "builtin", "scancode"], default=None,
                   help="licence-text scanner: builtin (always installed), scancode (the "
                        "[scan] extra) or auto (scancode when installed; default)")
    c.add_argument("--provenance-depth", type=int, default=None, metavar="N",
                   help="how many levels of declared parent datasets to follow (default 2)")
    c.add_argument("--no-licence", action="store_true",
                   help="skip licence consistency and provenance")
    c.add_argument("--no-sources", action="store_true",
                   help="do not read stated sources (GitHub repos, licence pages) for a licence")
    c.add_argument("--no-cache", action="store_true", help="do not use the on-disk HTTP cache")
    c.add_argument("--yes", "-y", action="store_true",
                   help="do not ask before reading the data of a repo with 100,000 or more files "
                        "(the warning is still printed and recorded in the report)")
    c.add_argument("--no-evidence", action="store_true",
                   help="terminal output without evidence URLs")
    c.add_argument("-q", "--quiet", action="store_true", help="no progress messages")
    c.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    s = from_env(Settings())
    if args.max_scan_bytes is not None:
        s.max_scan_bytes = parse_bytes(args.max_scan_bytes)
    if args.sample_rows is not None:
        s.sample_rows = args.sample_rows
    if args.max_download_bytes is not None:
        s.max_download_bytes = parse_bytes(args.max_download_bytes)
    if args.seed is not None:
        s.seed = args.seed
    if args.no_git_fetch:
        s.git_fetch = False
    if args.fetch_workers is not None:
        s.fetch_workers = max(1, args.fetch_workers)
    if args.max_links is not None:
        s.max_links = args.max_links
    if args.scanner is not None:
        s.scanner = args.scanner
    if args.provenance_depth is not None:
        s.provenance_depth = max(0, args.provenance_depth)
    s.check_licences = not args.no_licence
    s.check_sources = not args.no_sources
    s.full = args.full
    s.configs = args.configs
    if args.phone_region:
        s.phone_region = args.phone_region.upper()
    s.check_data = not args.no_data
    s.check_links = not args.no_links
    s.use_cache = not args.no_cache
    return s


def findings(report, statuses: list[str]) -> list:
    """Results whose status is one the user asked to fail on (a plain match, no judgement)."""
    return [r for r in report.results if r.status in set(statuses)]


def can_ask(args: argparse.Namespace) -> bool:
    """Ask before a large scan only in a terminal; never with --yes, in CI or in an Action."""
    if args.yes or os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return False
    try:
        return sys.stdin.isatty() and sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


def _warn_progress(progress, quiet: bool):
    """The large-repo warning is printed even with --quiet: it asks for a decision."""
    if not quiet:
        return progress

    def only_warning(msg: str) -> None:
        if msg.startswith("Large repo:"):
            print(f"datasetvet: {msg}", file=sys.stderr)

    return only_warning


def cmd_check(args: argparse.Namespace) -> int:
    from rich.console import Console

    from datasetvet.http import FetchError
    from datasetvet.hubs.base import UnknownRefError
    from datasetvet.hubs.huggingface import DatasetNotFound
    from datasetvet.licences.scanner import ScanCodeUnavailable
    from datasetvet.pipeline import run_check
    from datasetvet.report.json_out import write_json
    from datasetvet.report.markdown import write_markdown
    from datasetvet.report.terminal import render

    try:
        settings = settings_from_args(args)
    except ValueError as exc:
        print(f"datasetvet: {exc}", file=sys.stderr)
        return EXIT_USAGE
    err = Console(stderr=True, highlight=False, soft_wrap=True)
    started = time.monotonic()

    def progress(msg: str) -> None:
        if not args.quiet:
            err.print(f"[bright_black]  {time.monotonic() - started:6.1f}s  {msg}[/]",
                      markup=True, highlight=False)

    def confirm(_warning: str) -> bool:
        """The warning itself was printed as progress; only ask when someone can answer."""
        try:
            answer = input("Read the data anyway? [y/N] ")
        except EOFError:
            return True
        return answer.strip().lower() in ("y", "yes")

    try:
        report = run_check(args.ref, settings, progress=_warn_progress(progress, args.quiet),
                           confirm=None if not can_ask(args) else confirm)
    except ScanCodeUnavailable as exc:
        print(f"datasetvet: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except UnknownRefError as exc:
        print(f"datasetvet: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except (DatasetNotFound, FetchError) as exc:
        print(f"datasetvet: {exc}", file=sys.stderr)
        return EXIT_ERROR
    render(report, Console(highlight=False, soft_wrap=True), evidence=not args.no_evidence)
    if args.json:
        write_json(report, args.json)
        if not args.quiet:
            err.print(f"JSON report written to {args.json}")
    if args.md:
        write_markdown(report, args.md)
        if not args.quiet:
            err.print(f"Markdown report written to {args.md}")
    hits = findings(report, args.fail_on)
    if hits:
        print(f"datasetvet: --fail-on matched {len(hits)} result(s): "
              + "; ".join(f"{r.status} {r.title}" for r in hits[:10])
              + (" ..." if len(hits) > 10 else ""), file=sys.stderr)
        return EXIT_FINDINGS
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else
                        logging.WARNING, format="%(name)s: %(message)s")
    if args.command == "check":
        return cmd_check(args)
    return EXIT_USAGE  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
