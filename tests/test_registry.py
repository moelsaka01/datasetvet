import pytest

from datasetvet.http import Http
from datasetvet.hubs.base import UnknownRefError
from datasetvet.hubs.huggingface import HuggingFaceAdapter
from datasetvet.pipeline import build_registry


@pytest.fixture
def reg():
    return build_registry(Http(None, use_auth=False))


@pytest.mark.parametrize("ref,expected", [
    ("hf:stanfordnlp/imdb", ("stanfordnlp/imdb", None)),
    ("hf:datasets/stanfordnlp/imdb", ("stanfordnlp/imdb", None)),
    ("hf:stanfordnlp/imdb@refs/convert/parquet", ("stanfordnlp/imdb", "refs/convert/parquet")),
    ("hf:imdb", ("imdb", None)),
    ("https://huggingface.co/datasets/stanfordnlp/imdb", ("stanfordnlp/imdb", None)),
    ("https://huggingface.co/datasets/stanfordnlp/imdb/tree/abc123", ("stanfordnlp/imdb",
                                                                      "abc123")),
    ("https://huggingface.co/datasets/stanfordnlp/imdb/blob/main/README.md",
     ("stanfordnlp/imdb", "main")),
])
def test_hf_refs_go_to_hf_adapter(reg, ref, expected):
    adapter = reg.adapter_for(ref)
    assert adapter.name == "huggingface"
    assert HuggingFaceAdapter._parse(ref) == expected


@pytest.mark.parametrize("ref", ["kaggle:x/y", "https://github.com/org/repo",
                                 "https://huggingface.co/org/model", "hf:", "hf:a/b/c",
                                 "stanfordnlp/imdb"])
def test_unknown_ref_gives_clear_error(reg, ref):
    with pytest.raises(UnknownRefError, match="Supported forms"):
        reg.adapter_for(ref)
