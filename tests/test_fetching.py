"""The git and parallel fetch routes (checks/health/fetching.py, hubs/gitpack.py) must read
exactly what the one-file-at-a-time route reads."""

import json
import shutil
import subprocess
from dataclasses import asdict

import httpx2
import pytest
from test_scan import copy_fetch, make_split

from datasetvet.checks.health import fetching
from datasetvet.checks.health.fetching import Fetcher
from datasetvet.checks.health.runner import run_health
from datasetvet.checks.health.scan import iter_split, plan_scan
from datasetvet.config import Settings
from datasetvet.hubs.base import DataPlan, GitPlan, SplitFile, SplitSource
from datasetvet.hubs.gitpack import GitPack
from datasetvet.hubs.huggingface import HuggingFaceAdapter

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def make_remote(tmp_path, n=25):
    """A local git repo with n small CSV files; returns (url, sha, blob ids, split)."""
    repo = tmp_path / "remote"
    (repo / "data").mkdir(parents=True)
    for i in range(n):
        (repo / "data" / f"part-{i:02}.csv").write_bytes(f"a,b\n{i},x{i}\n{i},y\n".encode())
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "uploadpack.allowFilter", "true")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "data")
    sha = git(repo, "rev-parse", "HEAD").strip()
    ids = {}
    for line in git(repo, "ls-tree", "-r", "HEAD").splitlines():
        meta, path = line.split("\t", 1)
        ids[path] = meta.split()[2]
    files = [SplitFile(url=str(repo / p), path=p, size=(repo / p).stat().st_size, fmt="csv")
             for p in sorted(ids)]
    split = SplitSource("default", "train", files, rows=2 * n,
                        bytes=sum(f.size for f in files), source="original files",
                        revision=sha)
    return repo.as_uri(), sha, ids, split


class Recording:
    def __init__(self, fail=()):
        self.paths = []
        self.fail = set(fail)

    def __call__(self, f, dest):
        self.paths.append(f.path)
        if f.path in self.fail:
            raise OSError(f"cannot read {f.path}")
        out = dest / ("http-" + f.path.replace("/", "_"))
        shutil.copy(f.url, out)
        return out


def full_plan(splits):
    return plan_scan(splits, max_scan_bytes=10**9, sample_rows=10, seed=0)


@pytest.fixture
def file_git(monkeypatch):
    monkeypatch.setattr(GitPack, "protocols", ("https", "file"))


@needs_git
def test_git_serves_blobs_whose_id_and_size_match(tmp_path, file_git):
    url, sha, ids, split = make_remote(tmp_path)
    ids = dict(ids)
    ids["data/part-03.csv"] = "0" * 40  # the hub lists another blob: must not be used
    split.files[5].size += 1  # size differs from the blob: must not be used
    base = Recording()
    plan = full_plan([split])
    work = tmp_path / "work"
    work.mkdir()
    fetcher = Fetcher(base, [split], plan, work, workers=1,
                      git=GitPlan(url=url, sha=sha, blob_ids=ids, pack_estimate=10_000))
    try:
        assert fetcher.stats["git"] == "used"
        for f in split.files:
            out = fetcher(f, work)
            assert out.read_bytes() == (tmp_path / "remote" / f.path).read_bytes()
            out.unlink()
    finally:
        fetcher.close()
    assert sorted(base.paths) == ["data/part-03.csv", "data/part-05.csv"]
    assert fetcher.stats["git_files"] == 23 and fetcher.stats["http_files"] == 2


@needs_git
def test_git_failure_falls_back_to_http(tmp_path, file_git):
    _url, sha, ids, split = make_remote(tmp_path)
    missing = (tmp_path / "no-such-repo").as_uri()
    base = Recording()
    work = tmp_path / "work"
    work.mkdir()
    fetcher = Fetcher(base, [split], full_plan([split]), work,
                      git=GitPlan(url=missing, sha=sha, blob_ids=ids, pack_estimate=10_000))
    try:
        assert fetcher.stats["git"].startswith("failed, used HTTP instead")
        for f in split.files:
            assert fetcher(f, work).read_bytes() == (tmp_path / "remote" / f.path).read_bytes()
    finally:
        fetcher.close()
    assert len(base.paths) == len(split.files)


def test_git_not_used_for_few_files_or_a_large_pack(tmp_path):
    split = make_split(tmp_path, n_files=3)
    ids = {f.path: "a" * 40 for f in split.files}
    fetcher = Fetcher(copy_fetch, [split], full_plan([split]), tmp_path,
                      git=GitPlan(url="https://x", sha="b" * 40, blob_ids=ids,
                                  pack_estimate=1))
    assert fetcher.stats["git"].startswith("not used: 3 file(s)")
    many = make_split(tmp_path, "many", n_files=25, rows_per_file=10)
    ids = {f.path: "a" * 40 for f in many.files}
    capped = plan_scan([many], max_scan_bytes=1, sample_rows=10, seed=0,
                       max_download_bytes=1000)
    fetcher = Fetcher(copy_fetch, [many], capped, tmp_path,
                      git=GitPlan(url="https://x", sha="b" * 40, blob_ids=ids,
                                  pack_estimate=5000))
    assert fetcher.stats["git"].startswith("not used: the fetch would be up to 5,000 bytes")
    over = fetching.GIT_BUDGET + 1
    fetcher = Fetcher(copy_fetch, [many], full_plan([many]), tmp_path,
                      git=GitPlan(url="https://x", sha="b" * 40, blob_ids=ids,
                                  pack_estimate=over))
    assert fetcher.stats["git"].startswith("not used: the fetch would be")


def read_with(split, plan, fetch, work):
    errors = []
    vals = [v for ch in iter_split(split, plan, fetch, work, lambda f, e: errors.append(f.path))
            for v in ch.batch.column("i").to_pylist()]
    return vals, errors


def test_parallel_reads_the_same_rows_in_the_same_order(tmp_path):
    split = make_split(tmp_path, n_files=12, rows_per_file=200, rg=50)
    for kw in ({"max_scan_bytes": 10**9, "sample_rows": 10},
               {"max_scan_bytes": 1, "sample_rows": 700}):
        seq_plan = plan_scan([split], seed=3, **kw)
        par_plan = plan_scan([split], seed=3, **kw)
        (tmp_path / "a").mkdir(exist_ok=True)
        (tmp_path / "b").mkdir(exist_ok=True)
        want = read_with(split, seq_plan, copy_fetch, tmp_path / "a")
        fetcher = Fetcher(copy_fetch, [split], par_plan, tmp_path / "b", workers=4)
        try:
            got = read_with(split, par_plan, fetcher, tmp_path / "b")
        finally:
            fetcher.close()
        assert got == want
        assert par_plan.downloaded == seq_plan.downloaded


def test_fetching_ahead_never_exceeds_the_download_cap(tmp_path):
    split = make_split(tmp_path, n_files=10, rows_per_file=200)
    one = split.files[0].size
    cap = 3 * one + 10  # room for three files
    plan = plan_scan([split], max_scan_bytes=1, sample_rows=2000, seed=0,
                     max_download_bytes=cap)
    base = Recording()
    base_sizes = {f.path: f.size for f in split.files}
    fetcher = Fetcher(base, [split], plan, tmp_path, workers=8)
    try:
        read_with(split, plan, fetcher, tmp_path)
    finally:
        fetcher.close()
    assert sum(base_sizes[p] for p in base.paths) <= cap
    assert len(plan.capped) == 7


def test_a_failed_download_is_reported_for_that_file_only(tmp_path):
    split = make_split(tmp_path, n_files=6, rows_per_file=100)
    bad = split.files[2].path
    seq = read_with(split, full_plan([split]), Recording(fail=[bad]), tmp_path)
    fetcher = Fetcher(Recording(fail=[bad]), [split], full_plan([split]), tmp_path, workers=4)
    try:
        par = read_with(split, full_plan([split]), fetcher, tmp_path)
    finally:
        fetcher.close()
    assert par == seq and par[1] == [bad]


@needs_git
def test_run_health_results_are_identical_across_routes(tmp_path, file_git):
    url, sha, ids, split = make_remote(tmp_path)
    data = DataPlan([split], git=GitPlan(url=url, sha=sha, blob_ids=ids, pack_estimate=10_000))
    reports = []
    for git_fetch, workers in ((False, 1), (True, 8), (False, 8)):
        stats: dict = {}
        info, results = run_health(Recording(), data, Settings(git_fetch=git_fetch,
                                                               fetch_workers=workers),
                                   fetch_stats=stats)
        info.seconds = None
        reports.append(json.dumps([asdict(info)] + [asdict(r) for r in results],
                                  sort_keys=True, default=str))
        assert stats["git"] == ("used" if git_fetch else "not used")
    assert reports[0] == reports[1] == reports[2]


def test_hf_git_plan_lists_only_small_non_lfs_data_files(router, make_http):
    sha = "c" * 40
    router.json("https://datasets-server.huggingface.co/parquet", {"error": "x"}, 500)
    router.json("https://huggingface.co/api/datasets/o/d", {
        "id": "o/d", "sha": sha, "gated": False, "private": False, "cardData": {},
        "siblings": [
            {"rfilename": "README.md", "blobId": "r" * 40, "size": 30},
            {"rfilename": "data/train.csv", "blobId": "1" * 40, "size": 20},
            {"rfilename": "data/test.csv", "blobId": "2" * 40, "size": 20,
             "lfs": {"sha256": "x", "size": 20}},
            {"rfilename": "data/validation.csv", "blobId": "3" * 40,
             "size": 11 * 1024 * 1024}]})
    router.add(f"https://huggingface.co/datasets/o/d/resolve/{sha}/README.md",
               httpx2.Response(200, text="---\nlicense: mit\n---\n# D\n"))
    hf = HuggingFaceAdapter(make_http(router))
    ds = hf.resolve(f"hf:o/d@{sha}")
    plan = hf.splits(ds)
    assert plan.git is not None
    assert plan.git.url == "https://huggingface.co/datasets/o/d" and plan.git.sha == sha
    assert plan.git.blob_ids == {"data/train.csv": "1" * 40}
    # small blobs (README + train) + LFS pointer and large file (200 each) + trees
    assert plan.git.pack_estimate == 50 + 2 * 200 + 4 * 100
