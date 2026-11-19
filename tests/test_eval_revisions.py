"""Task 4.4: the audit-time card revision is the latest commit at or before the audit date."""

import json
import sys
from pathlib import Path

import httpx2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

from revisions import audit_revision

URL = "https://huggingface.co/api/datasets/org/ds/commits/main"


def commits(dates):
    return [{"id": f"{i:040x}", "date": d, "title": "t"} for i, d in dates]


def test_picks_latest_commit_before_audit(router, make_http):
    page0 = commits([(5, "2025-01-01T00:00:00.000Z"), (4, "2024-07-01T00:00:00.000Z")] * 25)
    page1 = commits([(3, "2024-05-30T10:00:00.000Z"), (2, "2024-05-01T00:00:00.000Z")])

    def handler(req):
        body = page1 if req.url.params.get("p") == "1" else page0
        link = {"link": f'<{URL}?p=1>; rel="next"'} if body is page0 else {}
        return httpx2.Response(200, content=json.dumps(body), headers=link)

    router.add(URL, handler)
    got = audit_revision(make_http(router), "org/ds", "2024-06-12T10:00:00-04:00")
    assert got["sha"] == f"{3:040x}" and got["date"].startswith("2024-05-30")


def test_no_commit_before_audit(router, make_http):
    router.json(URL, commits([(1, "2025-03-01T00:00:00.000Z")]))
    got = audit_revision(make_http(router), "org/ds", "2024-06-12T10:00:00-04:00")
    assert got["sha"] is None and "no commit" in got["note"]


def test_missing_repo(router, make_http):
    got = audit_revision(make_http(router), "org/ds", "2024-06-12T10:00:00-04:00")
    assert got["sha"] is None and "404" in got["note"]
