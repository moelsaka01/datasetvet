"""The status table in PLAN.md 5.4, reproduced with a local test server."""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from datasetvet.checks.links import LinkChecker, check_links, status_for_code
from datasetvet.config import Settings
from datasetvet.http import Http
from datasetvet.hubs.base import LinkRef


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _route(self, head: bool):
        p = self.path
        if p == "/robots.txt":
            return self._send(200, b"User-agent: *\nDisallow: /private\n", head)
        if p.startswith("/code/"):
            return self._send(int(p.rsplit("/", 1)[1]), b"x", head)
        if p == "/head-not-allowed":
            return self._send(405 if head else 200, b"ok", head)
        if p == "/redirect":
            return self._redirect("/code/200")
        if p == "/loop-a":
            return self._redirect("/loop-b")
        if p == "/loop-b":
            return self._redirect("/loop-a")
        if p == "/slow":
            time.sleep(1.5)
            return self._send(200, b"late", head)
        return self._send(404, b"", head)

    def _send(self, code, body, head):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        if code == 429:
            self.send_header("Retry-After", "0")
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _redirect(self, to):
        self.send_response(302)
        self.send_header("Location", to)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self._route(True)

    def do_GET(self):
        self._route(False)


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def checker():
    s = Settings(link_timeout=0.5, link_retries=1)
    return LinkChecker(Http(None, use_auth=False, sleep=lambda _s: None), s)


def check(checker, url):
    return checker.check(LinkRef(url=url, label="Homepage", stated=True))


@pytest.mark.parametrize("path,expected", [
    ("/code/200", "ok"), ("/code/204", "ok"),
    ("/code/404", "dead"), ("/code/410", "dead"),
    ("/code/401", "restricted"), ("/code/403", "restricted"), ("/code/451", "restricted"),
    ("/code/500", "unreachable"), ("/code/503", "unreachable"),
    ("/code/429", "unknown"), ("/code/418", "unknown"),
    ("/head-not-allowed", "ok"),
    ("/redirect", "ok"),
    ("/loop-a", "unknown"),
    ("/private/page", "unknown"),
])
def test_status_table(server, checker, path, expected):
    r = check(checker, server + path)
    assert r.status == expected, r.facts[0].text
    assert r.data["checked_at"]


def test_head_fallback_and_final_url_recorded(server, checker):
    r = check(checker, server + "/head-not-allowed")
    assert r.data["method"] == "GET" and r.data["code"] == 200
    r = check(checker, server + "/redirect")
    assert r.data["final_url"].endswith("/code/200") and "final URL" in r.facts[0].text


def test_robots_disallow_reported(server, checker):
    r = check(checker, server + "/private/x")
    assert r.data.get("robots_disallowed") and "robots.txt" in r.facts[0].text


def test_timeout_is_unreachable(server, checker):
    assert check(checker, server + "/slow").status == "unreachable"


def test_connection_refused_is_unreachable(checker):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert check(checker, f"http://127.0.0.1:{port}/").status == "unreachable"


def test_nxdomain_is_dead(checker, monkeypatch):
    def fail(*_a, **_k):
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
    monkeypatch.setattr(socket, "getaddrinfo", fail)
    r = check(checker, "http://no-such-host.invalid/")
    assert r.status == "dead" and "NXDOMAIN" in r.facts[0].text


def test_gated_hf_dataset_is_restricted(server):
    s = Settings(link_timeout=0.5, link_retries=0)
    http = Http(None, use_auth=False, sleep=lambda _s: None)
    lc = LinkChecker(http, s, gated_lookup=lambda ds_id: "auto")
    # emulate an HF dataset URL whose page answers 200
    import httpx2
    from conftest import Router
    router = Router()
    router.add("https://huggingface.co/datasets/org/gated", httpx2.Response(200, text="page"))
    lc.http = Http(None, use_auth=False, transport=httpx2.MockTransport(router),
                   sleep=lambda _s: None)
    r = lc.check(LinkRef(url="https://huggingface.co/datasets/org/gated", label="x",
                         stated=True))
    assert r.status == "restricted" and r.data["gated"] == "auto"


def test_status_for_code():
    assert status_for_code(200) == "ok" and status_for_code(302) == "unknown"


def test_max_links_limit(server, checker):
    links = [LinkRef(url=f"{server}/code/200?{i}", label="x", stated=False) for i in range(3)]
    results, nc = check_links(links, checker, max_links=2)
    assert len(results) == 2 and "1 links beyond" in nc[0]
