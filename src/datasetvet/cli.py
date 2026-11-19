"""Command-line entry point: `datasetvet check <ref>`. Phase 5 adds `badge`."""

from __future__ import annotations

import argparse
import logging
import sys
import time

from datasetvet import __version__
from datasetvet.config import Settings, from_env, parse_bytes

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datasetvet",
        description="Before you train on it, check it. Facts only, not legal advice.",
    )
    parser.add_argument("--version", action="version", version=f"datasetvet {__version__}")
    sub = parser.add_subparsers(dest="command")
    c = sub.add_parser("check", help="check a dataset and print a report",
                       description="Check a dataset: card, links and data health.")
    c.add_argument("ref", help="dataset reference, e.g. hf:stanfordnlp/imdb, "
                              "hf:org/name@revision or https://huggingface.co/datasets/org/name")
    c.add_argument("--json", metavar="PATH", help="also write the JSON report to PATH")
    c.add_argument("--max-scan-bytes", default=None,
                   help="full-scan limit (default 5GB); above it the data is sampled")
    c.add_argument("--sample-rows", type=int, default=None,
                   help="rows to sample above the limit (default 1,000,000)")
    c.add_argument("--seed", type=int, default=None, help="sampling seed (default 0)")
    c.add_argument("--full", action="store_true", help="scan every row whatever the size")
    c.add_argument("--config", action="append", dest="configs", metavar="NAME",
                   help="only scan this config (repeatable)")
    c.add_argument("--phone-region", metavar="XX",
                   help="also match national phone formats for region XX (e.g. GB, US)")
    c.add_argument("--no-data", action="store_true", help="skip the data-health scan")
    c.add_argument("--no-links", action="store_true", help="skip the link check")
    c.add_argument("--max-links", type=int, default=None, help="link-check limit (default 200)")
    c.add_argument("--no-cache", action="store_true", help="do not use the on-disk HTTP cache")
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
    if args.seed is not None:
        s.seed = args.seed
    if args.max_links is not None:
        s.max_links = args.max_links
    s.full = args.full
    s.configs = args.configs
    if args.phone_region:
        s.phone_region = args.phone_region.upper()
    s.check_data = not args.no_data
    s.check_links = not args.no_links
    s.use_cache = not args.no_cache
    return s


def cmd_check(args: argparse.Namespace) -> int:
    from rich.console import Console

    from datasetvet.http import FetchError
    from datasetvet.hubs.base import UnknownRefError
    from datasetvet.hubs.huggingface import DatasetNotFound
    from datasetvet.pipeline import run_check
    from datasetvet.report.json_out import write_json
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

    try:
        report = run_check(args.ref, settings, progress=progress)
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
