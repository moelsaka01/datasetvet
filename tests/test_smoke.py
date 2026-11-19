"""End to end, offline: a fake Hub serving a recorded card and synthetic Parquet files."""

import json

import httpx2
import pyarrow as pa
from conftest import HF_FIXTURES, hf_fixture, parquet_bytes

from datasetvet import __version__
from datasetvet.cli import main
from datasetvet.config import Settings
from datasetvet.http import Http
from datasetvet.pipeline import run_check
from datasetvet.report.json_out import read_json, write_json
from datasetvet.report.terminal import render

IMDB = "stanfordnlp/imdb"


def fake_imdb(router):
    # The recorded card is front matter only; add a small synthetic body with link bullets.
    fixture = HF_FIXTURES / "imdb"
    sha = json.loads((fixture / "info.json").read_text("utf-8"))["sha"]
    body = ("\n# IMDB\n\n- **Homepage:** http://ai.stanford.edu/~amaas/data/sentiment/\n"
            "- **Repository:** https://github.com/example/missing\n")
    router.add(f"https://huggingface.co/datasets/{IMDB}/resolve/{sha}/README.md",
               httpx2.Response(200, text=(fixture / "README.md").read_text("utf-8") + body))
    info = hf_fixture("imdb", router, IMDB)
    pq_body = json.loads((fixture / "parquet.json").read_text("utf-8"))["body"]
    tables = {
        "train": pa.table({"text": ["good film", "bad film", "good film", "mail me a@example.com"],
                           "label": [1, 0, 1, 1]}),
        "test": pa.table({"text": ["bad film", "fine", ""], "label": [1, 1, None]}),
        "unsupervised": pa.table({"text": ["meh"], "label": [-1]}),
    }
    names = {f"{f['config']}/{f['split']}/{f['filename']}" for f in pq_body["parquet_files"]}

    def serve(request):
        tail = "/".join(request.url.path.split("/")[-3:])
        if tail not in names:
            return httpx2.Response(404)
        return httpx2.Response(200, content=parquet_bytes(tables[tail.split("/")[1]]))

    router.add(f"https://huggingface.co/datasets/{IMDB}/resolve/", serve, method="GET")
    # links in the card: answer every outside host
    router.add("http://ai.stanford.edu", httpx2.Response(200))
    router.add("https://github.com", httpx2.Response(404))
    return info


def offline_http(router):
    return Http(None, use_auth=False, transport=httpx2.MockTransport(router),
                sleep=lambda _s: None)


def test_version_string():
    assert __version__ == "0.0.0"


def test_cli_without_command_prints_help(capsys):
    assert main([]) == 2
    assert "check" in capsys.readouterr().err


def test_end_to_end_offline(router, tmp_path):
    fake_imdb(router)
    report = run_check("hf:stanfordnlp/imdb", Settings(use_cache=False),
                       http=offline_http(router))
    by = {r.check: r for r in report.results}
    assert report.scan.kind == "full" and report.scan.rows_scanned == 8
    assert by["card.licence"].status == "present"
    assert by["health.duplicates"].status == "found"
    dup = next(f for f in by["health.duplicates"].facts if f.data.get("split") ==
               "plain_text/train")
    assert dup.data["extra_copies"] == 1
    leak = next(f for f in by["health.leakage"].facts if f.data.get("shared_inputs"))
    assert leak.data["pair"] == ["plain_text/test", "plain_text/train"]
    assert leak.data["label_differs"] == 1  # "bad film": 0 in train, 1 in test
    assert by["health.empty"].status == "found"
    assert by["health.pii"].status == "found"
    links = [r for r in report.results if r.family == "links"]
    assert {r.status for r in links} == {"ok", "dead"}
    assert any("Phase 3" in n for n in report.not_checked)

    path = tmp_path / "r.json"
    write_json(report, path)
    assert read_json(path) == report
    from rich.console import Console
    console = Console(record=True, width=200)
    render(report, console)
    text = console.export_text()
    assert text.splitlines()[0] == "Full scan"
    assert "Facts only, not legal advice" in text
    assert "jane" not in text and "a@example.com" not in text


def test_sampled_run_is_labelled(router):
    fake_imdb(router)
    report = run_check("hf:stanfordnlp/imdb",
                       Settings(use_cache=False, max_scan_bytes=1, sample_rows=4, seed=1),
                       http=offline_http(router))
    assert report.scan.kind == "sampled"
    assert report.scan.header().startswith("Sampled: ")
    assert "of 100,000 rows (seed 1)" in report.scan.header()
    dup = next(r for r in report.results if r.check == "health.duplicates")
    assert dup.data["scan"].startswith("Sampled")


def test_gated_end_to_end(router):
    hf_fixture("hle", router, "cais/hle")
    router.add("https://", httpx2.Response(200))
    report = run_check("hf:cais/hle", Settings(use_cache=False), http=offline_http(router))
    assert report.scan.kind == "not checked" and "gated" in report.scan.reason
    health = [r for r in report.results if r.family == "health"]
    assert health and {r.status for r in health} == {"not checked"}
