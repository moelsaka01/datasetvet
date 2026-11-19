"""Task 4.2: the launch runner resumes after a kill with no duplicate or missing rows."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "launch"))

from run import config_hash, run, tier_settings
from state import State

DATASETS = [{"id": f"org/ds{i}", "sha": f"{i:040d}"} for i in range(7)]


def test_kill_mid_batch_then_resume(tmp_path):
    calls = []

    def dying(ds):
        if len(calls) == 3:
            raise KeyboardInterrupt  # the process is killed while checking the 4th dataset
        calls.append(ds["id"])
        return "{}", 1

    state = State(tmp_path / "s.sqlite")
    with pytest.raises(KeyboardInterrupt):
        run(DATASETS, "A", state, "h1", dying, batch=2, say=lambda _m: None)
    state.close()

    state = State(tmp_path / "s.sqlite")  # a new process
    resumed = []

    def ok(ds):
        resumed.append(ds["id"])
        return "{}", 1

    assert run(DATASETS, "A", state, "h1", ok, say=lambda _m: None) == 4
    rows = state.rows("A")
    assert sorted(r["dataset_id"] for r in rows) == sorted(d["id"] for d in DATASETS)
    assert not set(calls) & set(resumed)  # nothing checked twice
    assert all(r["status"] == "done" for r in rows)


def test_failures_are_recorded_and_retried_on_request(tmp_path):
    state = State(tmp_path / "s.sqlite")

    def flaky(ds):
        if ds["id"] == "org/ds2":
            raise RuntimeError("boom")
        return "{}", 1

    run(DATASETS, "A", state, "h1", flaky, say=lambda _m: None)
    failed = [r for r in state.rows("A") if r["status"] == "failed"]
    assert [r["dataset_id"] for r in failed] == ["org/ds2"] and "boom" in failed[0]["error"]
    assert run(DATASETS, "A", state, "h1", flaky, say=lambda _m: None) == 0
    assert run(DATASETS, "A", state, "h1", lambda ds: ("{}", 1), retry_failed=True,
               say=lambda _m: None) == 1
    assert all(r["status"] == "done" for r in state.rows("A"))


def test_changed_config_or_revision_reruns(tmp_path):
    state = State(tmp_path / "s.sqlite")
    run(DATASETS, "A", state, "h1", lambda ds: ("{}", 1), say=lambda _m: None)
    assert run(DATASETS, "A", state, "h2", lambda ds: ("{}", 1), say=lambda _m: None) == 7
    moved = [dict(d, sha="f" * 40) if d["id"] == "org/ds0" else d for d in DATASETS]
    assert run(moved, "A", state, "h2", lambda ds: ("{}", 1), say=lambda _m: None) == 1


def test_max_and_stop_flag(tmp_path):
    state = State(tmp_path / "s.sqlite")
    assert run(DATASETS, "B", state, "h", lambda ds: ("{}", 1), max_n=3,
               say=lambda _m: None) == 3
    stop = {"now": True}
    assert run(DATASETS, "B", state, "h", lambda ds: ("{}", 1), stop=stop,
               say=lambda _m: None) == 0


def test_tier_settings_and_hash(tmp_path):
    a, b = tier_settings("A", tmp_path), tier_settings("B", tmp_path)
    assert not a.check_data and a.check_links and a.scanner == "builtin"
    assert b.check_data and not b.check_links and b.max_download_bytes
    assert config_hash("A", a, "x.json") != config_hash("B", b, "x.json")
    assert config_hash("A", a, "x.json") == config_hash("A", tier_settings("A", tmp_path),
                                                        "x.json")
