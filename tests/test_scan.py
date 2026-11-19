import shutil

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
