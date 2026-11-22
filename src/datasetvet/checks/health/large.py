"""Warning before a very large repo is scanned (PLAN.md task 5.9).

A repo with 100,000 or more files takes a long time to read in full. Before any data file is
fetched, say how many files the repo has, how long a full read is likely to take, and how to run
a sampled scan instead. The rates are the ones measured on one repo of 389,052 files
(RESULTS.md, "Time for a very large repo"); they are an estimate, and the text says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from datasetvet.checks.health.scan import plan_scan
from datasetvet.config import Settings
from datasetvet.hubs.base import DataPlan, Listing

LARGE_REPO_FILES = 100_000
# Measured 2026-11-22 on PGCodeLLM/radin-cyber-backups (RESULTS.md section 2): 34.7 ms a data
# file for a read over HTTP (`default/test`, 6,307 files). Files of other sizes will differ.
READ_SECONDS_PER_FILE = 0.0347
# The sampled read of the same repo: 321 s for 9,999 rows from a 100 MB download cap.
SAMPLED_FLAGS = "--max-scan-bytes 100MB --sample-rows 10000 --max-download-bytes 100MB"


@dataclass
class LargeRepo:
    files: int  # files listed in the repo
    at_least: bool  # the list was cut off, so the real count is higher
    data_files: int  # files the scan would read
    seconds: float | None  # estimated time of this run's read; None when it cannot be given
    kind: str  # "full" or "sampled": what the scan planner would do with the current settings

    def short(self) -> str:
        return f"large repo: {'at least ' if self.at_least else ''}{self.files:,} files"

    def text(self) -> str:
        n = f"{'at least ' if self.at_least else ''}{self.files:,}"
        out = (f"Large repo: {n} files ({self.data_files:,} of them data files that would be "
               "read).")
        if self.seconds is None:
            out += " The time for this read cannot be estimated."
        elif self.kind == "full":
            out += (f" A full read would take about {_duration(self.seconds)} at the "
                    f"{READ_SECONDS_PER_FILE * 1000:.1f} ms a file measured on one repo of "
                    "389,052 files; yours will differ with file sizes.")
        else:
            out += (f" This run is a sampled scan; the files it needs would take about "
                    f"{_duration(self.seconds)} at {READ_SECONDS_PER_FILE * 1000:.1f} ms a "
                    "file (an estimate).")
        if self.kind == "full":
            out += (f" For a few minutes instead, run a sampled scan: {SAMPLED_FLAGS} "
                    "(measured: about 5 minutes on that repo).")
        return out


def _duration(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} seconds"
    if seconds < 5400:
        return f"{seconds / 60:.0f} minutes"
    return f"{seconds / 3600:.1f} hours"


def large_repo(listing: Listing, data: DataPlan, settings: Settings) -> LargeRepo | None:
    """None when the repo is under the limit or there is nothing to read."""
    files = len(listing.files)
    if files < LARGE_REPO_FILES or data.not_checked or not data.splits:
        return None
    splits = data.splits
    if settings.configs:
        splits = [s for s in splits if s.config in settings.configs]
        if not splits:
            return None
    plan = plan_scan(splits, max_scan_bytes=settings.max_scan_bytes,
                     sample_rows=settings.sample_rows, seed=settings.seed,
                     force_full=settings.full, max_download_bytes=settings.max_download_bytes)
    data_files = sum(len(s.files) for s in splits)
    needed = float(data_files)
    if plan.mode == "sampled":
        # a sample stops when its quota is full: files needed = quota / rows per file
        needed = 0.0
        for s in splits:
            quota = plan.quotas.get(s.key)
            if not s.files:
                continue
            if quota and s.rows:
                needed += min(len(s.files), quota * len(s.files) / s.rows)
            else:
                needed += len(s.files)
        if plan.download_cap:
            capped = _files_in_cap(splits, plan.download_cap)
            needed = min(needed, capped)
    seconds = needed * READ_SECONDS_PER_FILE if data_files else None
    return LargeRepo(files=files, at_least=not listing.complete, data_files=data_files,
                     seconds=seconds, kind=plan.mode)


def _files_in_cap(splits: list, cap: int) -> float:
    """How many files fit under a download cap, from the listed sizes (average size)."""
    sized = [f.size for s in splits for f in s.files if f.size]
    if not sized:
        return float("inf")
    return cap / (sum(sized) / len(sized))
