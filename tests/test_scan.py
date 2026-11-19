import shutil
from itertools import pairwise

import pyarrow as pa
from conftest import parquet_bytes

from datasetvet.checks.health.scan import iter_split, plan_scan
from datasetvet.hubs.base import SplitFile, SplitSource


def make_split(tmp_path, name="train", n_files=3, rows_per_file=1000, rg=100):
    files = []
    for i in range(n_files):
        p = tmp_path / f"{name}-{i}.parquet"
        start = i * rows_per_file
        p.write_bytes(parquet_bytes(pa.table({"i": list(range(start, start + rows_per_file))}),
                                    row_group_size=rg))
        files.append(SplitFile(url=str(p), path=p.name, size=p.stat().st_size, fmt="parquet"))
    return SplitSource("c", name, files, rows=n_files * rows_per_file,
                       bytes=sum(f.size for f in files), source="parquet conversion",
                       revision="r")


def copy_fetch(f, dest):
    out = dest / ("copy-" + f.path)
    shutil.copy(f.url, out)
    return out


def read_all(split, plan, tmp_path, errors=None):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    vals = []
    for ch in iter_split(split, plan, copy_fetch, work,
                         lambda f, e: (errors if errors is not None else []).append((f, e))):
        vals += ch.batch.column("i").to_pylist()
    return vals


def test_full_scan_under_limit(tmp_path):
    s = make_split(tmp_path)
    plan = plan_scan([s], max_scan_bytes=10**9, sample_rows=100, seed=0)
    assert plan.mode == "full" and plan.header(3000) == "Full scan"
    assert read_all(s, plan, tmp_path) == list(range(3000))


def test_sample_is_deterministic_and_labelled(tmp_path):
    s = make_split(tmp_path)
    plan = plan_scan([s], max_scan_bytes=1, sample_rows=250, seed=42)
    assert plan.mode == "sampled"
    a = read_all(s, plan, tmp_path)
    b = read_all(s, plan_scan([s], max_scan_bytes=1, sample_rows=250, seed=42), tmp_path)
    c = read_all(s, plan_scan([s], max_scan_bytes=1, sample_rows=250, seed=7), tmp_path)
    assert a == b and a != c
    assert len(a) == 250 and len(set(a)) == 250
    assert plan.header(len(a)) == "Sampled: 250 of 3,000 rows (seed 42)"


def test_sample_quota_is_proportional_to_rows(tmp_path):
    big = make_split(tmp_path, "train", n_files=3)
    small = make_split(tmp_path, "test", n_files=1)
    plan = plan_scan([big, small], max_scan_bytes=1, sample_rows=400, seed=0)
    assert plan.quotas == {"c/train": 300, "c/test": 100}


def test_force_full(tmp_path):
    s = make_split(tmp_path)
    plan = plan_scan([s], max_scan_bytes=1, sample_rows=10, seed=0, force_full=True)
    assert plan.mode == "full" and plan.reason == "--full given"


def test_corrupt_file_reported_and_scan_continues(tmp_path):
    s = make_split(tmp_path, n_files=2)
    (tmp_path / s.files[0].path).write_bytes(b"not a parquet file")
    errors = []
    vals = read_all(s, plan_scan([s], max_scan_bytes=10**9, sample_rows=1, seed=0), tmp_path,
                    errors)
    assert vals == list(range(1000, 2000))
    assert len(errors) == 1 and errors[0][0].path == s.files[0].path


def test_temp_files_deleted(tmp_path):
    s = make_split(tmp_path, n_files=2)
    read_all(s, plan_scan([s], max_scan_bytes=10**9, sample_rows=1, seed=0), tmp_path)
    assert list((tmp_path / "work").iterdir()) == []


def test_csv_and_jsonl(tmp_path):
    (tmp_path / "a.csv").write_text("x,y\n1,a\n2,b\n")
    (tmp_path / "b.jsonl").write_text('{"x": 3, "y": "c"}\n{"x": 4, "y": "d"}\n')
    (tmp_path / "c.json").write_text('[{"x": 5, "y": "e"}]')
    files = [SplitFile(str(tmp_path / n), n, 1, fmt) for n, fmt in
             (("a.csv", "csv"), ("b.jsonl", "jsonl"), ("c.json", "json"))]
    split = SplitSource("d", "train", files, None, 3, "original files", "r")
    work = tmp_path / "work"
    work.mkdir()
    xs = []
    for ch in iter_split(split, plan_scan([split], max_scan_bytes=10**9, sample_rows=1, seed=0),
                         copy_fetch, work, lambda f, e: (_ for _ in ()).throw(e)):
        xs += ch.batch.column("x").to_pylist()
    assert xs == [1, 2, 3, 4, 5]


def test_choose_chunks_is_exact_and_spread():
    from datasetvet.checks.health.scan import choose_chunks

    ch = choose_chunks(10_000, 1_000, "k", 10)
    assert sum(n for _a, n in ch) == 1_000 and len(ch) == 100
    assert ch == sorted(ch)
    assert all(a + n <= b for (a, n), (b, _m) in pairwise(ch))
    assert ch[0][0] < 1_000 and ch[-1][0] > 9_000  # from both ends of the file
    assert choose_chunks(10_000, 1_000, "k", 10) == ch
    assert choose_chunks(50, 80, "k", 10) == [(0, 50)]


def test_sample_spreads_across_a_sorted_file(tmp_path):
    # one file of 10,000 rows in 2 row groups; a 1,000-row sample used to be one row group
    s = make_split(tmp_path, n_files=1, rows_per_file=10_000, rg=5_000)
    plan = plan_scan([s], max_scan_bytes=1, sample_rows=1_000, seed=3)
    vals = read_all(s, plan, tmp_path)
    assert len(vals) == 1_000 and len(set(vals)) == 1_000
    assert min(vals) < 1_000 and max(vals) > 9_000
    first_half = sum(v < 5_000 for v in vals)
    assert 350 < first_half < 650  # both row groups contribute


def test_csv_is_sampled_in_chunks(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("x\n" + "".join(f"{i}\n" for i in range(5_000)))
    split = SplitSource("d", "train", [SplitFile(str(p), "a.csv", p.stat().st_size, "csv")],
                        5_000, 10**9, "original files", "r")
    plan = plan_scan([split], max_scan_bytes=1, sample_rows=500, seed=0)
    work = tmp_path / "work"
    work.mkdir()
    xs = []
    for ch in iter_split(split, plan, copy_fetch, work, lambda f, e: (_ for _ in ()).throw(e)):
        assert ch.batch.column("x").to_pylist()[0] == ch.first_row
        xs += ch.batch.column("x").to_pylist()
    assert len(xs) == 500 and min(xs) < 500 and max(xs) > 4_500
