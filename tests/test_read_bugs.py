"""Three datasetvet bugs found by the Phase 4 launch scan, each with a test written first:

1. a nanosecond timestamp that does not fit a Python datetime stopped the whole scan
   (`trentmkelly/polymarket_historical_data`: ValueError);
2. pyarrow's JSON reader can build an invalid array, and the error (ArrowIndexError) stopped
   the whole scan (`Yshh525/rho-internalize-v1-20261021`, `neurodeskorg/webapps`);
3. a JSON array whose items are not objects raised AttributeError, and the file was then
   counted as "corrupt" (8 datasets).
"""

import datetime as dt
import json

import pyarrow as pa
from conftest import parquet_bytes
from test_scan import copy_fetch

from datasetvet.checks.health.runner import run_health
from datasetvet.config import Settings
from datasetvet.hubs.base import DataPlan, SplitFile, SplitSource


def scan(tmp_path, files: dict[str, bytes | str], fmt: str):
    """Run data health over `files` (name -> content), all one split, read as `fmt`."""
    sfiles = []
    for name, content in files.items():
        p = tmp_path / name
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
        sfiles.append(SplitFile(url=str(p), path=name, size=p.stat().st_size, fmt=fmt))
    split = SplitSource("default", "train", sfiles, rows=None,
                        bytes=sum(f.size for f in sfiles), source="original files",
                        revision="r")
    info, results = run_health(copy_fetch, DataPlan([split]), Settings(git_fetch=False,
                                                                       fetch_workers=1))
    return info, {r.check: r for r in results}


def dup_extra(by) -> int:
    return sum(f.data.get("extra_copies", 0) for f in by["health.duplicates"].facts)


# -- 1. nanosecond timestamps ------------------------------------------------------------------

NS = 1_794_666_945_608_406_404  # from trentmkelly/polymarket_historical_data: not a whole µs


def test_nanosecond_timestamps_do_not_stop_the_scan(tmp_path):
    table = pa.table({"t": pa.array([NS, NS + 1, NS], type=pa.timestamp("ns")),
                      "x": [1, 2, 1]})
    info, by = scan(tmp_path, {"a.parquet": parquet_bytes(table)}, "parquet")
    assert info.rows_scanned == 3
    # rows 0 and 2 are equal; row 1 differs from row 0 by one nanosecond only
    assert dup_extra(by) == 1


def test_timestamps_that_differ_by_a_nanosecond_are_not_duplicates(tmp_path):
    table = pa.table({"t": pa.array([NS, NS + 1], type=pa.timestamp("ns"))})
    _, by = scan(tmp_path, {"a.parquet": parquet_bytes(table)}, "parquet")
    assert dup_extra(by) == 0


def test_nanosecond_timestamps_inside_structs_and_lists(tmp_path):
    ts = pa.timestamp("ns", tz="UTC")
    rows = [{"ev": {"at": NS, "tags": [NS, NS + 5]}}, {"ev": {"at": NS, "tags": [NS, NS + 5]}},
            {"ev": None}]
    table = pa.Table.from_pylist(rows, schema=pa.schema([
        ("ev", pa.struct([("at", ts), ("tags", pa.list_(ts))]))]))
    info, by = scan(tmp_path, {"a.parquet": parquet_bytes(table)}, "parquet")
    assert info.rows_scanned == 3 and dup_extra(by) == 1


def test_ordinary_timestamps_are_unchanged(tmp_path):
    d = dt.datetime(2026, 1, 2, 3, 4, 5, 6)
    table = pa.table({"t": pa.array([d, d], type=pa.timestamp("us"))})
    _, by = scan(tmp_path, {"a.parquet": parquet_bytes(table)}, "parquet")
    assert dup_extra(by) == 1


# -- 2. pyarrow's JSON reader builds an invalid array ------------------------------------------

BAD_ARROW_JSON = '{"runs": {"Np": {"steps": {"cos_start": [null, null]}}}}'


def test_pyarrow_json_reader_really_builds_an_invalid_array():
    """The premise of bug 2: if a pyarrow release fixes this, the fallback is just unused."""
    import io

    import pyarrow.json as pj
    import pytest

    t = pj.read_json(io.BytesIO(BAD_ARROW_JSON.encode()))
    try:
        t.to_pylist()
    except Exception:  # noqa: BLE001  ArrowIndexError in pyarrow 26
        return
    pytest.skip("this pyarrow reads the file correctly")


def test_invalid_array_from_pyarrow_does_not_stop_the_scan(tmp_path):
    files = {"good.json": '[{"a": 1}]', "bad.json": BAD_ARROW_JSON}
    info, by = scan(tmp_path, files, "json")
    assert info.rows_scanned == 2  # the file is read, by the fallback reader
    assert by["health.unreadable"].status == "none found"


def test_the_fallback_reads_what_the_json_says(tmp_path):
    info, by = scan(tmp_path, {"bad.json": BAD_ARROW_JSON,
                               "bad2.json": BAD_ARROW_JSON}, "json")
    assert info.rows_scanned == 2 and dup_extra(by) == 1  # the two identical rows


def test_a_pretty_printed_json_lines_file_still_reads(tmp_path):
    text = json.dumps({"a": 1, "b": [None, None]}, indent=1) + "\n" + json.dumps(
        {"a": 2, "b": [None, None]}, indent=1)
    info, _ = scan(tmp_path, {"x.jsonl": text}, "jsonl")
    assert info.rows_scanned == 2


# -- 3. JSON arrays whose items are not objects ------------------------------------------------

def test_json_array_of_strings_is_one_row_per_item(tmp_path):
    info, by = scan(tmp_path, {"a.json": json.dumps(["x", "y", "x"])}, "json")
    assert info.rows_scanned == 3
    assert by["health.unreadable"].status == "none found"
    assert dup_extra(by) == 1


def test_json_array_of_lists_is_one_row_per_item(tmp_path):
    info, by = scan(tmp_path, {"a.json": json.dumps([[1, 2], [3], [1, 2]])}, "json")
    assert info.rows_scanned == 3 and dup_extra(by) == 1
    assert by["health.unreadable"].status == "none found"


def test_json_array_mixing_objects_and_non_objects_is_reported_not_crashed(tmp_path):
    info, by = scan(tmp_path, {"a.json": json.dumps([{"a": 1}, "x"]),
                               "b.json": json.dumps([{"a": 2}])}, "json")
    assert info.rows_scanned == 1  # b.json is read
    res = by["health.unreadable"]
    assert res.status == "found" and "a.json" in res.facts[0].text
    assert "AttributeError" not in res.facts[0].text
    assert "objects and non-objects" in res.facts[0].text


def test_json_array_of_mixed_scalar_types_is_reported_as_a_reader_limit(tmp_path):
    _, by = scan(tmp_path, {"a.json": json.dumps([1, "x"])}, "json")
    res = by["health.unreadable"]
    assert res.status == "found" and res.facts[0].data["kind"] == "reader_limit"


def test_empty_json_array_has_no_rows_and_is_not_an_error(tmp_path):
    info, by = scan(tmp_path, {"a.json": "[]", "b.json": '[{"a": 1}]'}, "json")
    assert info.rows_scanned == 1 and by["health.unreadable"].status == "none found"
