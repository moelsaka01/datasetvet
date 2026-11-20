"""How data files get from the hub to the scanner: one git fetch for many small files, and
several HTTP downloads at once for the rest. Neither changes what is read.

The scanner (`scan.iter_split`) still asks for one file at a time, in its own order, and
decides which files to read; this module only makes each answer arrive sooner.

- git route (`settings.git_fetch`): when the hub says the files can come from git
  (`DataPlan.git`), at least GIT_MIN_FILES of them qualify and the whole fetch is at most
  GIT_BUDGET bytes (and, for a capped sampled scan, at most the download cap), the pinned
  commit's small blobs are fetched once. A file is then served from git only if its blob id
  is the one the hub lists for that path and its size matches; otherwise it is downloaded.
  Any git failure falls back to HTTP for every file.
- parallel route (`settings.fetch_workers` > 1): files that are downloaded are fetched up
  to `fetch_workers` at a time, ahead of the scanner, in the scanner's own order. A file is
  fetched ahead only if its size is known and, under a download cap, it still fits after
  everything already read or in flight, so the cap is never exceeded by fetching ahead.
  Files fetched ahead but not read (the scanner stopped early) are deleted with the temp
  dir; that is at most one window of files.

Errors keep their meaning: a failed download raises the same FetchError when the scanner
asks for that file, so it is reported exactly as before.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from datasetvet.checks.health.scan import ScanPlan, file_order
from datasetvet.hubs.base import GitPlan, SplitFile, SplitSource, local_name
from datasetvet.hubs.gitpack import GitError, GitPack, git_executable

GIT_MIN_FILES = 20  # below this, one request per file is cheap enough
GIT_BUDGET = 256 * 1024 * 1024  # never fetch a pack larger than this (by the hub's sizes)

Fetch = Callable[[SplitFile, Path], Path]


class Fetcher:
    """Callable like an adapter's `fetch(file, dest_dir)`; call `close()` when done."""

    def __init__(self, base: Fetch, splits: list[SplitSource], plan: ScanPlan, tmpdir: Path,
                 *, workers: int = 1, git: GitPlan | None = None, use_git: bool = True,
                 say: Callable[[str], None] | None = None):
        self.base = base
        self.plan = plan
        self.tmpdir = Path(tmpdir)
        self.order: list[SplitFile] = [s.files[i] for s in splits for i in file_order(s, plan)]
        self.index = {f.url: i for i, f in enumerate(self.order)}
        self.stats: dict[str, Any] = {"workers": max(1, workers), "git": "not used",
                                      "git_files": 0, "http_files": 0, "fetched_ahead": 0}
        self.pack: GitPack | None = None
        self.blob_ids: dict[str, str] = {}
        self._lock = threading.Lock()
        self._futures: dict[int, Future[Path]] = {}
        self._inflight: dict[int, int] = {}  # position -> size, fetched ahead, not yet read
        self._next = 0  # first position not yet considered for fetching ahead
        if use_git and git is not None:
            self._start_git(git, say or (lambda _m: None))
        self.pool = (ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fetch")
                     if workers > 1 else None)

    # -- git -----------------------------------------------------------------------------
    def _git_reason(self, git: GitPlan) -> str | None:
        wanted = sum(1 for f in self.order if f.path in git.blob_ids)
        if wanted < GIT_MIN_FILES:
            return f"{wanted} file(s) git could serve, fewer than {GIT_MIN_FILES}"
        limit = GIT_BUDGET
        if self.plan.download_cap is not None:
            limit = min(limit, self.plan.download_cap)
        if git.pack_estimate > limit:
            return f"the fetch would be up to {git.pack_estimate:,} bytes, over {limit:,}"
        if git_executable() is None:
            return "git is not installed"
        return None

    def _start_git(self, git: GitPlan, say: Callable[[str], None]) -> None:
        reason = self._git_reason(git)
        if reason:
            self.stats["git"] = f"not used: {reason}"
            return
        say("fetching the small files with git")
        pack = GitPack(git.url, git.sha, self.tmpdir / "git", git=git_executable() or "git")
        try:
            pack.fetch(max_blob=git.max_blob)
        except GitError as exc:
            pack.close()
            self.stats["git"] = f"failed, used HTTP instead: {exc}"
            return
        self.pack = pack
        self.blob_ids = git.blob_ids
        self.stats.update(git="used", git_pack_bytes=pack.pack_bytes)

    def _from_git(self, f: SplitFile, dest_dir: Path) -> Path | None:
        oid = self.blob_ids.get(f.path)
        if self.pack is None or oid is None:
            return None
        data = self.pack.read(oid)
        if data is None or (f.size is not None and len(data) != f.size):
            return None
        dest = Path(dest_dir) / local_name(f.path)
        dest.write_bytes(data)
        return dest

    def _git_serves(self, f: SplitFile) -> bool:
        oid = self.blob_ids.get(f.path)
        return self.pack is not None and oid is not None and oid in self.pack.blobs

    # -- one file --------------------------------------------------------------------------
    def _get(self, f: SplitFile, dest_dir: Path) -> Path:
        got = self._from_git(f, dest_dir)
        if got is not None:
            with self._lock:
                self.stats["git_files"] += 1
            return got
        with self._lock:
            self.stats["http_files"] += 1
        return self.base(f, dest_dir)

    def _slot(self, pos: int) -> Path:
        d = self.tmpdir / "fetch" / str(pos)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -- fetching ahead --------------------------------------------------------------------
    def _fill(self, pos: int) -> None:
        """Start downloads for files after `pos` while the window has room."""
        assert self.pool is not None
        workers = self.stats["workers"]
        self._next = max(self._next, pos + 1)
        while len(self._futures) < workers and self._next < len(self.order):
            j = self._next
            f = self.order[j]
            if self._git_serves(f):
                self._next += 1
                continue  # read from the local pack when asked; nothing to download
            if f.size is None:
                return  # unknown size: the cap cannot be respected ahead of time
            cap = self.plan.download_cap
            if cap is not None and (self.plan.downloaded + sum(self._inflight.values())
                                    + f.size > cap):
                return
            self._inflight[j] = f.size
            self._futures[j] = self.pool.submit(self._get, f, self._slot(j))
            self.stats["fetched_ahead"] += 1
            self._next += 1

    def __call__(self, f: SplitFile, dest_dir: Path) -> Path:
        pos = self.index.get(f.url)
        if self.pool is None or pos is None:
            return self._get(f, dest_dir)
        fut = self._futures.pop(pos, None)
        # the file asked for counts as in flight until the scanner adds it to
        # plan.downloaded, so nothing fetched ahead can push the total over the cap
        known = f.size is not None or self._git_serves(f)
        if fut is None and not self._git_serves(f) and f.size is not None:
            self._inflight[pos] = f.size
        if known or self.plan.download_cap is None:
            self._fill(pos)
        self._inflight.pop(pos, None)
        if fut is None:
            return self._get(f, self._slot(pos))
        return fut.result()

    def close(self) -> None:
        if self.pool is not None:
            self.pool.shutdown(wait=True, cancel_futures=True)
            self.pool = None
        if self.pack is not None:
            self.pack.close()
