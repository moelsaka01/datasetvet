"""The Hub's file listing stops at 100,000 entries (found in the Phase 4 launch scan).

datasetvet must page through the tree API when `siblings` has that many entries, never treat
a truncated list as complete, and say "Partial" when a full listing is not possible.
"""

import json
from urllib.parse import parse_qs, urlsplit

import httpx2
import pyarrow as pa
from conftest import parquet_bytes

from datasetvet.config import Settings
from datasetvet.hubs.huggingface import LISTING_CAP, HuggingFaceAdapter
from datasetvet.model import ScanInfo
from datasetvet.pipeline import run_check

SHA = "d" * 40
PAGE = 1000
API = "https://huggingface.co/api/datasets/o/big"


def _name(i: int) -> str:
    return f"data/part-{i:06}.parquet"


def sibling(i: int) -> dict:
    return {"rfilename": _name(i), "size": 100, "blobId": f"{i:040x}"}


def tree_entry(i: int) -> dict:
    return {"type": "file", "oid": f"{i:040x}", "size": 100, "path": _name(i)}


def serve_big_repo(router, total: int, *, readme: str = "---\nlicense: mit\n---\n# D\n",
                   fail_page: int | None = None, same_cursor: bool = False,
                   foreign_next: bool = False) -> list[str]:
    """A repo with `total` files. `siblings` stops at LISTING_CAP like the real Hub; the tree
    API serves PAGE entries per page with a `Link: rel="next"` header. Returns the tree URLs
    requested, in order."""
    siblings = [{"rfilename": "README.md", "size": 30, "blobId": "e" * 40}]
    siblings += [sibling(i) for i in range(min(total, LISTING_CAP - 1))]
    seen: list[str] = []

    def tree(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        q = parse_qs(urlsplit(str(request.url)).query)
        page = int(q.get("cursor", ["0"])[0])
        if fail_page is not None and page == fail_page:
            return httpx2.Response(500, text="boom")
        items = [{"type": "file", "oid": "e" * 40, "size": 30, "path": "README.md"}] \
            if page == 0 else []
        lo, hi = page * PAGE, min(total, (page + 1) * PAGE)
        items += [tree_entry(i) for i in range(lo, hi)]
        if page == 0:
            items.append({"type": "directory", "oid": "f" * 40, "size": 0, "path": "data"})
        headers = {}
        if hi < total:
            nxt = page if same_cursor else page + 1
            host = "https://evil.example" if foreign_next else "https://huggingface.co"
            headers["Link"] = (f'<{host}/api/datasets/o/big/tree/{SHA}?recursive=true'
                               f'&expand=false&limit={PAGE}&cursor={nxt}>; rel="next"')
        return httpx2.Response(200, json=items, headers=headers)

    router.add(f"{API}/tree/{SHA}", tree)
    router.json(f"{API}/refs", {"converts": []})
    router.json(API, {"id": "o/big", "sha": SHA, "gated": False, "private": False,
                      "cardData": {}, "siblings": siblings})
    router.add(f"https://huggingface.co/datasets/o/big/resolve/{SHA}/README.md",
               httpx2.Response(200, text=readme))
    router.json("https://datasets-server.huggingface.co/parquet", {"error": "x"}, 500)
    return seen


def test_listing_under_the_cap_needs_no_tree_request(router, make_http):
    seen = serve_big_repo(router, LISTING_CAP - 2)  # 99,998 data files + README = 99,999 entries
    hf = HuggingFaceAdapter(make_http(router))
    ds = hf.resolve(f"hf:o/big@{SHA}")
    listing = hf.listing(ds)
    assert listing.complete and len(listing.files) == LISTING_CAP - 1
    assert seen == []


def test_listing_at_the_cap_pages_through_the_tree(router, make_http):
    total = LISTING_CAP + 543  # 100,543 data files
    seen = serve_big_repo(router, total)
    hf = HuggingFaceAdapter(make_http(router))
    ds = hf.resolve(f"hf:o/big@{SHA}")
    listing = hf.listing(ds)
    assert listing.complete
    paths = [f.path for f in listing.files]
    assert len(paths) == total + 1 and len(set(paths)) == len(paths)  # + README.md
    assert _name(total - 1) in paths and _name(LISTING_CAP + 100) in paths
    assert "data" not in paths  # directories are not files
    assert len(seen) == -(-total // PAGE)  # one request per page of 1,000
    assert hf.files(ds) == listing.files


def test_a_repo_of_exactly_the_cap_is_complete_not_assumed_cut(router, make_http):
    serve_big_repo(router, LISTING_CAP - 1)  # README + 99,999 = 100,000 siblings: at the cap
    hf = HuggingFaceAdapter(make_http(router))
    listing = hf.listing(hf.resolve(f"hf:o/big@{SHA}"))
    assert listing.complete and len(listing.files) == LISTING_CAP


def test_a_failing_tree_page_makes_the_listing_incomplete(router, make_http):
    serve_big_repo(router, LISTING_CAP + 5000, fail_page=3)
    hf = HuggingFaceAdapter(make_http(router))
    listing = hf.listing(hf.resolve(f"hf:o/big@{SHA}"))
    assert not listing.complete
    assert "incomplete" in listing.note and "HTTP 500" in listing.note
    assert len(listing.files) == LISTING_CAP  # what the Hub's own list had, nothing invented


def test_a_repeated_cursor_does_not_loop_forever(router, make_http):
    seen = serve_big_repo(router, LISTING_CAP + 5000, same_cursor=True)
    hf = HuggingFaceAdapter(make_http(router))
    listing = hf.listing(hf.resolve(f"hf:o/big@{SHA}"))
    assert not listing.complete and "loop" in listing.note
    assert len(seen) <= 3


def test_a_next_link_to_another_host_is_not_followed(router, make_http):
    serve_big_repo(router, LISTING_CAP + 5000, foreign_next=True)
    hf = HuggingFaceAdapter(make_http(router))
    listing = hf.listing(hf.resolve(f"hf:o/big@{SHA}"))
    assert not listing.complete
    assert not any("evil.example" in str(r.url) for r in router.calls)


def test_an_incomplete_listing_is_never_cached_as_complete(router, make_http):
    serve_big_repo(router, LISTING_CAP + 5000, fail_page=1)
    hf = HuggingFaceAdapter(make_http(router))
    ds = hf.resolve(f"hf:o/big@{SHA}")
    assert hf.listing(ds) is hf.listing(ds) and not hf.listing(ds).complete


# -- what the checks do with it ----------------------------------------------------------------

CARD_LAST_FILE = ("---\nlicense: mit\nconfigs:\n- config_name: default\n  data_files:\n"
                  "  - split: train\n    path: {path}\n---\n# D\n")


def link_settings() -> Settings:
    return Settings(check_data=False, check_licences=False, check_links=True, use_cache=False)


def test_no_false_missing_file_beyond_the_old_cut_off(router, make_http):
    total = LISTING_CAP + 543
    serve_big_repo(router, total, readme=CARD_LAST_FILE.format(path=_name(total - 1)))
    report = run_check(f"hf:o/big@{SHA}", link_settings(), http=make_http(router))
    assert [r for r in report.results if r.family == "links"] == []  # the file exists


def test_missing_file_is_still_reported_when_the_listing_is_complete(router, make_http):
    serve_big_repo(router, LISTING_CAP + 5,
                   readme=CARD_LAST_FILE.format(path="data/nope-*.parquet"))
    report = run_check(f"hf:o/big@{SHA}", link_settings(), http=make_http(router))
    dead = [r for r in report.results if r.family == "links"]
    assert len(dead) == 1 and dead[0].status == "dead"


def test_incomplete_listing_never_gives_a_missing_file_result(router, make_http):
    serve_big_repo(router, LISTING_CAP + 5000, fail_page=2,
                   readme=CARD_LAST_FILE.format(path=_name(LISTING_CAP + 4000)))
    report = run_check(f"hf:o/big@{SHA}", link_settings(), http=make_http(router))
    assert [r for r in report.results if r.family == "links"] == []
    assert any("data_files" in n and "incomplete" in n for n in report.not_checked)


def data_settings() -> Settings:
    return Settings(check_licences=False, check_links=False, use_cache=False, git_fetch=False,
                    max_scan_bytes=10**9)


def serve_small_files(router) -> None:
    body = parquet_bytes(pa.table({"x": [1, 2, 3]}))
    router.add(f"https://huggingface.co/datasets/o/big/resolve/{SHA}/data/",
               lambda _r: httpx2.Response(200, content=body), method="GET")


def test_full_listing_beyond_the_cap_gives_a_full_scan(router, make_http):
    total = LISTING_CAP + 30
    serve_big_repo(router, total, readme="---\nlicense: mit\nconfigs:\n- config_name: default\n"
                   "  data_files:\n  - split: train\n    path: data/part-10002[0-9].parquet\n"
                   "---\n")
    serve_small_files(router)
    report = run_check(f"hf:o/big@{SHA}", data_settings(), http=make_http(router))
    assert report.scan.listing_complete
    assert report.scan.header().startswith("Full scan")
    assert report.scan.rows_scanned == 3 * 10  # part-100020 .. part-100029, past the old cut


def test_incomplete_listing_is_labelled_partial_not_full(router, make_http):
    serve_big_repo(router, LISTING_CAP + 5000, fail_page=1,
                   readme="---\nlicense: mit\nconfigs:\n- config_name: default\n"
                   "  data_files:\n  - split: train\n    path: data/part-00001[0-9].parquet\n"
                   "---\n")
    serve_small_files(router)
    http = make_http(router)
    report = run_check(f"hf:o/big@{SHA}", data_settings(), http=http)
    assert report.scan.kind == "full" and not report.scan.listing_complete
    assert "Partial" in report.scan.header() and "Full scan" not in report.scan.header()
    assert report.scan.header().startswith("Partial scan")
    assert any("file list" in n for n in report.settings["data_notes"])
    # every data-health result carries the same label
    health = [r for r in report.results if r.family == "health"]
    assert health and all(r.data["scan"].startswith("Partial scan") for r in health)


def test_scan_info_header_for_a_sample_of_a_partial_listing():
    info = ScanInfo(kind="sampled", rows_scanned=10, rows_total=100, seed=0,
                    listing_complete=False)
    assert info.header().startswith("Sampled: 10 of 100 rows (seed 0)")
    assert "partial file list" in info.header()
    assert ScanInfo(kind="full").header() == "Full scan"  # unchanged when the list is complete




def test_scan_info_round_trips_with_the_new_field():
    from datasetvet.model import ScanInfo as S

    a = S(kind="full", listing_complete=False)
    assert S.from_dict(json.loads(json.dumps(a.__dict__))) == a
    assert S.from_dict({"kind": "full"}).listing_complete is True  # reports from before
