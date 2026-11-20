"""Read many small repo files with one git fetch instead of one HTTP request each.

Hugging Face keeps files that are not in LFS as ordinary git blobs. A shallow fetch of the
pinned commit with `--filter=blob:limit=<n>` returns all of them in one packfile (measured:
a repo with 46,388 small files in about 2 s, against about 1 s per file over HTTP). The
blobs are then read from git's object store with `git cat-file --batch`.

Safety and exactness:
- The repo is a bare one in a temp dir: no working copy is written, so nothing from the
  dataset lands on disk as files, and no repo hooks exist or run.
- git runs with prompts off, credential helpers cleared and only https allowed. No token is
  given to git; a gated repo simply fails and the caller falls back to HTTP.
- A blob is used only when its git object id equals the `blobId` the Hub lists for that
  path at that revision, so the bytes are exactly that file. A missing blob (LFS file,
  above the limit) returns None and the caller downloads the file over HTTP as before.

The Hub's git server only answers small batches of explicit blob ids (about 10), so a
"fetch only these files" request is not used; the caller bounds the one-shot fetch by the
Hub's listed sizes instead (see `datasetvet.checks.health.fetching`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path


def git_config(protocols: tuple[str, ...]) -> list[str]:
    cfg = ["-c", "credential.helper=", "-c", "protocol.allow=never",
           "-c", "advice.detachedHead=false"]
    for proto in protocols:
        cfg += ["-c", f"protocol.{proto}.allow=always"]
    return cfg


class GitError(Exception):
    pass


def git_executable() -> str | None:
    return shutil.which("git")


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GIT_ASKPASS="",
               SSH_ASKPASS="", GIT_NO_LAZY_FETCH="1", GIT_LFS_SKIP_SMUDGE="1")
    return env


class GitPack:
    """One shallow, blob-size-filtered fetch of `url` at commit `sha` into `workdir`."""

    protocols: tuple[str, ...] = ("https",)  # tests add "file"

    def __init__(self, url: str, sha: str, workdir: Path, git: str = "git"):
        self.url = url
        self.sha = sha
        self.dir = Path(workdir)
        self.git = git
        self.blobs: dict[str, int] = {}  # object id -> size, for blobs in the pack
        self.pack_bytes = 0
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    def _cmd(self) -> list[str]:
        return [self.git, *git_config(self.protocols)]

    def _run(self, *args: str, timeout: float) -> str:
        try:
            p = subprocess.run([*self._cmd(), *args], capture_output=True, timeout=timeout,
                               env=_env(), stdin=subprocess.DEVNULL, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitError(f"git {args[0] if args else ''}: {type(exc).__name__}") from exc
        if p.returncode != 0:
            err = p.stderr.decode("utf-8", "replace").strip().splitlines()
            raise GitError(f"git exit {p.returncode}: {err[-1] if err else ''}"[:200])
        return p.stdout.decode("utf-8", "replace")

    def fetch(self, max_blob: int, timeout: float = 600.0) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        d = str(self.dir)
        self._run("init", "-q", "--bare", d, timeout=60)
        self._run("-C", d, "remote", "add", "origin", self.url, timeout=60)
        self._run("-C", d, "fetch", "-q", "--no-tags", "--depth", "1",
                  f"--filter=blob:limit={max_blob}", "origin", self.sha, timeout=timeout)
        out = self._run("-C", d, "cat-file", "--batch-all-objects",
                        "--batch-check=%(objectname) %(objecttype) %(objectsize)", timeout=300)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[1] == "blob":
                self.blobs[parts[0]] = int(parts[2])
        self.pack_bytes = sum(p.stat().st_size for p in (self.dir / "objects").rglob("*")
                              if p.is_file())

    def read(self, oid: str) -> bytes | None:
        """The blob's bytes, or None when it is not in the pack."""
        if oid not in self.blobs:
            return None
        with self._lock:
            if self._proc is None:
                self._proc = subprocess.Popen(
                    [*self._cmd(), "-C", str(self.dir), "cat-file", "--batch"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, env=_env())
            proc = self._proc
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(oid.encode() + b"\n")
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            if len(header) != 3 or header[1] != b"blob":
                return None
            size = int(header[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)  # trailing newline
            return data if len(data) == size else None

    def close(self) -> None:
        with self._lock:
            if self._proc is not None:
                try:
                    if self._proc.stdin:
                        self._proc.stdin.close()
                    self._proc.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    self._proc.kill()
                    self._proc.wait()
                if self._proc.stdout:
                    self._proc.stdout.close()
                self._proc = None
