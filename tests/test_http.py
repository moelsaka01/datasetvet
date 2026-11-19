import httpx2
import pytest

import datasetvet.http as http_mod
from datasetvet.http import FetchError, Http, RateLimiter, classify_exception, parse_ratelimit

API = "https://huggingface.co/api/datasets/x/y"


def rl(r: int, t: int, q: int = 500, name: str = "api") -> dict:
    return {"RateLimit": f'"{name}";r={r};t={t}',
            "RateLimit-Policy": f'"fixed window";"{name}";q={q};w=300'}


def test_parse_ratelimit_headers():
    h = {k.lower(): v for k, v in rl(499, 209).items()}
    assert parse_ratelimit(h) == ("api", 499, 209, 500, 300)


def test_no_pause_above_20_percent(router, make_http):
    router.add(API, httpx2.Response(200, json={}, headers=rl(400, 100)))
    sleeps: list[float] = []
    http = make_http(router, sleeps=sleeps)
    for _ in range(3):
        http.get(API)
    assert sleeps == []


def test_pauses_when_remaining_below_20_percent():
    clock = [0.0]
    sleeps: list[float] = []
    lim = RateLimiter(sleep=sleeps.append, clock=lambda: clock[0])
    lim.update("huggingface.co:api", {k.lower(): v for k, v in rl(50, 100).items()})
    lim.before("huggingface.co:api")
    # 50 left of 500 (10%), 100 s to reset: spread out, 100/50 = 2 s per request
    assert sleeps == [pytest.approx(2.0)]


def test_waits_full_window_when_none_left():
    sleeps: list[float] = []
    lim = RateLimiter(sleep=sleeps.append, clock=lambda: 0.0)
    lim.update("huggingface.co:api", {k.lower(): v for k, v in rl(0, 37).items()})
    lim.before("huggingface.co:api")
    assert sleeps == [37]


def test_429_honours_ratelimit_t_then_retries(router, make_http):
    responses = iter([httpx2.Response(429, headers=rl(0, 42)),
                      httpx2.Response(200, json={"ok": 1}, headers=rl(499, 300))])
    router.add(API, lambda _r: next(responses))
    sleeps: list[float] = []
    http = make_http(router, sleeps=sleeps)
    assert http.get_json(API) == {"ok": 1}
    assert 42 in sleeps


def test_429_retry_after_header_wins(router, make_http):
    responses = iter([httpx2.Response(429, headers={"Retry-After": "7"}),
                      httpx2.Response(200, json={})])
    router.add(API, lambda _r: next(responses))
    sleeps: list[float] = []
    make_http(router, sleeps=sleeps).get(API)
    assert sleeps == [7.0]


def test_429_gives_up_after_three_retries(router, make_http):
    router.add(API, httpx2.Response(429, headers={"Retry-After": "1"}))
    resp = make_http(router).get(API)
    assert resp.status == 429
    assert len(router.calls) == 4


def test_cache_hit_skips_network(router, make_http):
    router.add(API, httpx2.Response(200, json={"v": 1}))
    http = make_http(router, cache=True)
    assert http.get_json(API, ttl=float("inf")) == {"v": 1}
    again = http.get(API, ttl=float("inf"))
    assert again.from_cache and again.json() == {"v": 1}
    assert len(router.calls) == 1
    http.get(API)  # ttl=None never reads the cache
    assert len(router.calls) == 2


def test_5xx_retried_then_returned(router, make_http):
    router.add(API, httpx2.Response(503))
    resp = make_http(router).get(API, retries=2)
    assert resp.status == 503 and len(router.calls) == 3


def test_redirect_loop_raises(router, make_http):
    router.add("https://a.example/1", httpx2.Response(302, headers={"Location": "/2"}))
    router.add("https://a.example/2", httpx2.Response(302, headers={"Location": "/1"}))
    with pytest.raises(FetchError) as err:
        make_http(router).get("https://a.example/1")
    assert err.value.kind == "redirect-loop"


def test_token_only_sent_to_hf_hosts_across_redirects(router, tmp_path, monkeypatch):
    monkeypatch.setattr(http_mod, "_hf_auth_headers", lambda: {"authorization": "Bearer T"})
    router.add("https://huggingface.co/datasets/x/y/resolve/abc/README.md",
               httpx2.Response(302, headers={"Location": "https://cdn.example.com/file"}))
    router.add("https://cdn.example.com/file", httpx2.Response(200, text="hi"))
    http = Http(None, transport=httpx2.MockTransport(router), sleep=lambda _s: None)
    assert http.authenticated
    assert http.get("https://huggingface.co/datasets/x/y/resolve/abc/README.md").text == "hi"
    first, second = router.calls
    assert first.headers.get("authorization") == "Bearer T"
    assert "authorization" not in second.headers
    http.get("https://example.org/page")
    assert "authorization" not in router.calls[-1].headers


def test_user_agent_has_no_personal_data(router, make_http):
    router.add(API, httpx2.Response(200, json={}))
    make_http(router).get(API)
    ua = router.calls[0].headers["user-agent"]
    assert ua.startswith("datasetvet/") and "@" not in ua


def test_dns_failure_classified():
    import socket

    exc = httpx2.ConnectError("x")
    exc.__cause__ = socket.gaierror(socket.EAI_NONAME, "not known")
    assert classify_exception(exc) == "dns"
    assert classify_exception(httpx2.ReadTimeout("t")) == "timeout"
    assert classify_exception(httpx2.ConnectError("refused")) == "connect"
