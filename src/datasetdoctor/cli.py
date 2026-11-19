"""Command-line entry point. Phase 2 (task 2.12) adds `check`; Phase 5 adds `badge`."""

from __future__ import annotations

import argparse
import sys

from datasetdoctor import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datasetdoctor",
        description="Before you train on it, check it. Facts only, not legal advice.",
    )
    parser.add_argument("--version", action="version", version=f"datasetdoctor {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print("datasetdoctor: nothing is implemented yet (Phase 1). See PLAN.md.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
