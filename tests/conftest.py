from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path

import httpx2
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from datasetvet.http import Http

FIXTURES = Path(__file__).parent / "fixtures"
HF_FIXTURES = FIXTURES / "hf"


class Router:
    """A MockTransport handler: (method, url-prefix) -> response factory. Counts calls."""

    def __init__(self) -> None:
        self.routes: list[tuple[str, str, Callable[[httpx2.Request], httpx2.Response]]] = []
        self.calls: list[httpx2.Request] = []

    def add(self, prefix: str, fn: Callable[[httpx2.Request], httpx2.Response] | httpx2.Response,
            method: str = "*") -> None:
        handler = fn if callable(fn) else (lambda _r, resp=fn: resp)
        self.routes.append((method, prefix, handler))

    def json(self, prefix: str, body, status: int = 200, headers: dict | None = None) -> None:
        self.add(prefix, lambda _r: httpx2.Response(status, json=body, headers=headers or {}))

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.calls.append(request)
        url = str(request.url)
        for method, prefix, fn in self.routes:
            if (method in ("*", request.method)) and url.startswith(prefix):
                return fn(request)
        return httpx2.Response(404, text=f"no route for {url}")


@pytest.fixture
def router() -> Router:
    return Router()


@pytest.fixture
def make_http(tmp_path):
    def factory(router: Router, *, cache: bool = False, sleeps: list | None = None) -> Http:
        sl = sleeps if sleeps is not None else []
        return Http(tmp_path / "cache" if cache else None, use_auth=False,
                    transport=httpx2.MockTransport(router), sleep=sl.append)
    return factory


def parquet_bytes(table: pa.Table, row_group_size: int | None = None) -> bytes:
    buf = io.BytesIO()
    pq.write_table(table, buf, row_group_size=row_group_size)
    return buf.getvalue()


def hf_fixture(name: str, router: Router, ds_id: str) -> dict:
    """Serve a recorded dataset's API responses through the router. Returns info.json."""
    d = HF_FIXTURES / name
    info = json.loads((d / "info.json").read_text("utf-8"))
    sha = info["sha"]
    router.json(f"https://huggingface.co/api/datasets/{ds_id}/refs",
                json.loads((d / "refs.json").read_text("utf-8"))["body"])
    router.json(f"https://huggingface.co/api/datasets/{ds_id}", info)
    readme = d / "README.md"
    if readme.exists():
        router.add(f"https://huggingface.co/datasets/{ds_id}/resolve/{sha}/README.md",
                   httpx2.Response(int((d / "readme_status.txt").read_text()),
                                   content=readme.read_bytes()))
    for ep in ("parquet", "size"):
        rec = json.loads((d / f"{ep}.json").read_text("utf-8"))
        router.json(f"https://datasets-server.huggingface.co/{ep}?dataset=", rec["body"],
                    rec["status"])
    return info
