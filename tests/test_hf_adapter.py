"""HF adapter against recorded responses (tests/fixtures/hf, re-record with record.py)."""

import httpx2
import pytest
from conftest import hf_fixture, parquet_bytes

from datasetvet.hubs.huggingface import (
    DatasetNotFound,
    HuggingFaceAdapter,
    infer_split,
    map_data_files,
    missing_data_files,
)


def test_imdb_resolve_card_and_conversion(router, make_http):
    info = hf_fixture("imdb", router, "stanfordnlp/imdb")
    hf = HuggingFaceAdapter(make_http(router))
    ds = hf.resolve("hf:stanfordnlp/imdb")
    assert ds.revision == info["sha"] and ds.gated is False
    card = hf.card(ds)
    assert card.metadata["license"] == ["other"]
    assert card.key_lines["license"] > 1
    assert card.evidence.url.endswith(f"/blob/{info['sha']}/README.md")
    plan = hf.splits(ds, card)
    assert plan.not_checked is None
    assert [s.key for s in plan.splits] == ["plain_text/test", "plain_text/train",
                                            "plain_text/unsupervised"]
    train = plan.splits[1]
    assert train.rows == 25000 and train.source == "parquet conversion"
    # pinned to the conversion branch's commit, not the moving ref
    assert "refs%2Fconvert" not in train.files[0].url and train.revision in train.files[0].url
    assert train.label_columns == ["label"] and train.label_names["label"] == ["neg", "pos"]


def test_gated_dataset_data_not_checked(router, make_http):
    hf_fixture("hle", router, "cais/hle")
    hf = HuggingFaceAdapter(make_http(router))
    ds = hf.resolve("hf:cais/hle")
    assert ds.gated == "auto"
    card = hf.card(ds)
    assert card.metadata.get("license") == "mit"
    plan = hf.splits(ds, card)
    assert plan.splits == [] and "gated" in plan.not_checked
    assert "never accepts terms" in plan.not_checked


def test_no_conversion_falls_back_to_original_files(router, make_http):
    hf_fixture("simready", router, "nvidia/simready-assets")
    hf = HuggingFaceAdapter(make_http(router))
    ds = hf.resolve("hf:nvidia/simready-assets")
    plan = hf.splits(ds)
    # The owner disabled the Dataset Viewer and the card has no `configs`, so there is no
    # statement of which files are data; package-metadata .json files are not guessed at.
    assert plan.splits == []
    assert "Dataset Viewer is disabled" in plan.not_checked


def test_original_csv_files_are_read_when_no_conversion(router, make_http, tmp_path):
    sha = "c" * 40
    router.json("https://huggingface.co/api/datasets/o/d/refs", {"converts": []})
    router.json("https://huggingface.co/api/datasets/o/d", {
        "id": "o/d", "sha": sha, "gated": False, "private": False,
        "siblings": [{"rfilename": "README.md"}, {"rfilename": "data/train.csv", "size": 20},
                     {"rfilename": "data/test.csv", "size": 20}],
        "cardData": {}})
    router.add(f"https://huggingface.co/datasets/o/d/resolve/{sha}/README.md",
               httpx2.Response(200, text="---\nlicense: mit\n---\n# D\n"))
    router.json("https://datasets-server.huggingface.co/parquet", {"error": "x"}, 500)
    router.add(f"https://huggingface.co/datasets/o/d/resolve/{sha}/data/train.csv",
               httpx2.Response(200, text="a,b\n1,x\n"))
    hf = HuggingFaceAdapter(make_http(router))
    ds = hf.resolve("hf:o/d")
    plan = hf.splits(ds)
    assert [(s.key, s.source) for s in plan.splits] == [("default/test", "original files"),
                                                        ("default/train", "original files")]
    local = hf.fetch(plan.splits[1].files[0], tmp_path)
    assert local.read_text() == "a,b\n1,x\n"


def test_not_found_is_clear(router, make_http):
    router.json("https://huggingface.co/api/datasets/nope/nope", {"error": "x"}, 401)
    with pytest.raises(DatasetNotFound, match="not found"):
        HuggingFaceAdapter(make_http(router)).resolve("hf:nope/nope")


def test_map_data_files_from_configs_and_convention():
    configs = [{"config_name": "a", "data_files": [{"split": "train", "path": "a/train-*"},
                                                   {"split": "test", "path": ["a/test-*"]}]},
               {"config_name": "b", "data_files": "b/*.jsonl"}]
    paths = ["a/train-0.parquet", "a/test-0.parquet", "b/x.jsonl"]
    assert map_data_files(configs, paths) == {
        ("a", "train"): ["a/train-0.parquet"], ("a", "test"): ["a/test-0.parquet"],
        ("b", "train"): ["b/x.jsonl"]}
    assert missing_data_files(configs + [{"config_name": "c", "data_files": "c/*.csv"}],
                              paths) == [("c", "c/*.csv")]
    assert infer_split("data/validation-00000.parquet") == "validation"
    assert infer_split("dev.jsonl") == "validation"
    assert infer_split("corpus.csv") == "train"


def test_label_names_from_parquet_metadata(tmp_path):
    import json

    import pyarrow as pa
    import pyarrow.parquet as pq

    from datasetvet.checks.health.labels import labels_from_hf_features
    from datasetvet.checks.health.scan import hf_features

    t = pa.table({"text": ["a"], "label": [0]})
    t = t.replace_schema_metadata({"huggingface": json.dumps({"info": {"features": {
        "text": {"dtype": "string", "_type": "Value"},
        "label": {"names": ["neg", "pos"], "_type": "ClassLabel"}}}})})
    p = tmp_path / "x.parquet"
    p.write_bytes(parquet_bytes(t))
    feats = hf_features(pq.ParquetFile(p).schema_arrow)
    assert labels_from_hf_features(feats) == {"label": ["neg", "pos"]}


@pytest.mark.network
def test_live_imdb_resolves_and_has_conversion():
    from datasetvet.http import Http

    hf = HuggingFaceAdapter(Http(None))
    ds = hf.resolve("hf:stanfordnlp/imdb")
    assert len(ds.revision) == 40
    plan = hf.splits(ds)
    assert {s.split for s in plan.splits} >= {"train", "test"}
