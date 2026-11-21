"""The old "corrupt data" check (Phase 4 found it overstated what it measured).

It now says what it measures: files the reader could not read as rows, with the kind of
failure. Files that are not data (tokenizer and config JSON, dependency folders) are never
read, so they cannot be counted.
"""

import json
import re

import httpx2
import pyarrow as pa
from conftest import parquet_bytes
from test_read_bugs import scan

from datasetvet.checks.health.runner import HEALTH_CHECKS, run_health
from datasetvet.config import Settings
from datasetvet.http import FetchError
from datasetvet.hubs.base import DataPlan, SplitFile, SplitSource
from datasetvet.hubs.huggingface import HuggingFaceAdapter, is_non_data_path

SHA = "c" * 40


def test_check_is_named_for_what_it_measures():
    assert "health.corrupt" not in HEALTH_CHECKS
    assert HEALTH_CHECKS["health.unreadable"] == "Files that could not be read as rows"


def test_wording_never_says_corrupt(tmp_path):
    _, by = scan(tmp_path, {"a.json": "{not json", "b.json": '[{"a": 1}]'}, "json")
    res = by["health.unreadable"]
    text = " ".join([res.title] + [f.text for f in res.facts])
    assert res.status == "found" and "corrupt" not in text.lower()
    assert "could not be read as rows" in res.facts[0].text


def test_kinds_of_failure(tmp_path):
    files = {"syntax.json": "{not json", "empty.jsonl": "", "mixed.jsonl": '{"a": 1}\n{"a": "x"}',
             "ok.jsonl": '{"a": 1}'}
    _, by = scan(tmp_path, files, "jsonl")
    kinds = {f.data["path"]: f.data["kind"] for f in by["health.unreadable"].facts if f.data}
    assert kinds == {"syntax.json": "invalid", "empty.jsonl": "empty",
                     "mixed.jsonl": "reader_limit"}


def test_a_truncated_parquet_file_is_invalid(tmp_path):
    data = parquet_bytes(pa.table({"a": list(range(100))}))
    _, by = scan(tmp_path, {"cut.parquet": data[: len(data) // 2]}, "parquet")
    facts = by["health.unreadable"].facts
    assert facts[0].data["kind"] == "invalid" and facts[0].data["path"] == "cut.parquet"


def test_a_failed_download_is_kind_download(tmp_path):
    f = SplitFile("x://y", "a.csv", 1, "csv")
    split = SplitSource("default", "train", [f], None, 1, "original files", "r")

    def boom(_f, _dest):
        raise FetchError("http", "HTTP 404", "x://y")

    _, results = run_health(boom, DataPlan([split]), Settings(git_fetch=False, fetch_workers=1))
    res = next(r for r in results if r.check == "health.unreadable")
    assert res.facts[0].data["kind"] == "download"
    assert "HTTP 404" in res.facts[0].text


def test_the_unreadable_files_make_the_other_results_partial(tmp_path):
    info, by = scan(tmp_path, {"a.json": "{not json", "b.json": '[{"a": 1}]'}, "json")
    assert info.partial and by["health.duplicates"].data["partial"] is True


# -- files that are not data -----------------------------------------------------------------

def test_non_data_paths():
    for p in ("tokenizer.json", "x/tokenizer_config.json", "config.json", "a/b/config.json",
              "special_tokens_map.json", "vocab.json", "generation_config.json",
              "preprocessor_config.json", "dataset_infos.json", "package.json",
              "package-lock.json", "tsconfig.json", "model.safetensors.index.json",
              "env/lib/python3.11/site-packages/botocore/data/a.json",
              "x/node_modules/y/z.json", "x/__pycache__/a.json"):
        assert is_non_data_path(p), p
    for p in ("data/train.json", "train.jsonl", "config/train.json", "my_config.json",
              "data/part-00001.parquet", "tokenizer/train.csv"):
        assert not is_non_data_path(p), p


def serve(router, files, card="---\nlicense: mit\n---\n"):
    router.json("https://huggingface.co/api/datasets/o/d/refs", {"converts": []})
    router.json("https://huggingface.co/api/datasets/o/d", {
        "id": "o/d", "sha": SHA, "gated": False, "private": False, "cardData": {},
        "siblings": [{"rfilename": "README.md"}] + [{"rfilename": f, "size": 10} for f in files]})
    router.add(f"https://huggingface.co/datasets/o/d/resolve/{SHA}/README.md",
               httpx2.Response(200, text=card))
    router.json("https://datasets-server.huggingface.co/parquet", {"error": "x"}, 500)


def test_non_data_files_are_not_planned_when_the_card_does_not_name_them(router, make_http):
    serve(router, ["train.jsonl", "tokenizer.json", "config.json",
                   "venv/lib/python3.11/site-packages/x/data.json"])
    hf = HuggingFaceAdapter(make_http(router))
    plan = hf.splits(hf.resolve(f"hf:o/d@{SHA}"))
    assert [f.path for s in plan.splits for f in s.files] == ["train.jsonl"]
    note = " ".join(plan.notes)
    assert "3 file(s) that are not data" in note and "tokenizer.json" in note


def test_the_card_can_name_a_file_that_would_otherwise_be_skipped(router, make_http):
    card = ("---\nconfigs:\n- config_name: default\n  data_files:\n  - split: train\n"
            "    path: config.json\n---\n")
    serve(router, ["config.json", "tokenizer.json"], card)
    hf = HuggingFaceAdapter(make_http(router))
    plan = hf.splits(hf.resolve(f"hf:o/d@{SHA}"))
    assert [f.path for s in plan.splits for f in s.files] == ["config.json"]


def test_a_repo_with_only_non_data_json_is_not_checked(router, make_http):
    serve(router, ["tokenizer.json", "config.json", "vocab.json"])
    hf = HuggingFaceAdapter(make_http(router))
    plan = hf.splits(hf.resolve(f"hf:o/d@{SHA}"))
    assert plan.splits == []
    assert re.search(r"no data files.*tokenizer|not data", plan.not_checked)


def test_report_json_uses_the_new_check_name(tmp_path):
    _, by = scan(tmp_path, {"a.jsonl": '{"a": 1}'}, "jsonl")
    assert "health.unreadable" in by and "health.corrupt" not in by
    assert by["health.unreadable"].status == "none found"
    assert json.dumps(by["health.unreadable"].facts[0].text)
