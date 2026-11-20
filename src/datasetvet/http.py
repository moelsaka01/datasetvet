"""The single HTTP session (PLAN.md sections 3, 10). Task 2.2.

- RateLimit-header limiter per bucket: reads `RateLimit: "api";r=..;t=..` and
  `RateLimit-Policy: ..;q=..;w=..`; when remaining r falls under 20% of q, requests in that
  bucket are spread over the reset window (sleep t / r before each one).
- 429: sleeps until `Retry-After` (or the RateLimit `t`), at most 3 retries.
- Connection errors and 5xx: `retries` retries with backoff.
- On-disk cache for GETs the caller marks cacheable (revision-pinned URLs).
- Redirects are followed by hand so the Hugging Face token is attached only to Hugging Face
  hosts, on every hop, and never sent to any other host.

Tokens are never read here except through `huggingface_hub.get_token()`, never logged, never
written to the cache, and never put in a report: reports show only "authenticated: yes/no".
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx2

from datasetvet import __version__
from datasetvet.model import now_iso

log = logging.getLogger("datasetvet.http")

USER_AGENT = f"datasetvet/{__version__} (dataset report CLI; +https://pypi.org/project/datasetvet/)"
HF_HOSTS = frozenset({"huggingface.co", "datasets-server.huggingface.co"})
# The Hub's download CDN (signed redirects from /resolve/, e.g. us.aws.cdn.hf.co). It is built
# for bulk downloads, so the one-request-per-second spacing for other hosts does not apply;
# RateLimit headers and 429s still do.
HF_CDN_SUFFIX = ".hf.co"
LOW_WATER = 0.20  # pace a bucket once r < 20% of q
MAX_429_RETRIES = 3
MAX_429_SLEEP = 300.0
MAX_REDIRECTS = 5

_RL_RE = re.compile(r'"?([A-Za-z0-9_-]+)"?\s*;\s*r=(\d+)\s*;\s*t=(\d+)')
_POLICY_RE = re.compile(r'"([A-Za-z0-9_-]+)"\s*;\s*q=(\d+)\s*;\s*w=(\d+)')


class FetchError(Exception):
    """Network failure after retries. kind: 'dns', 'timeout', 'connect', 'redirect-loop',
    'too-many-redirects', 'protocol'."""

    def __init__(self, kind: str, message: str, url: str):
        super().__init__(f"{kind}: {message} ({url})")
        self.kind = kind
        self.message = message
        self.url = url


@dataclass
class Response:
    status: int
    url: str  # final URL after redirects
    headers: dict[str, str]
    content: bytes
    fetched_at: str
    history: list[tuple[int, str]] = field(default_factory=list)
    from_cache: bool = False
    truncated: bool = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass
class _Bucket:
    q: int | None = None
    w: int | None = None
    r: int | None = None
    t: int | None = None
    seen_at: float = 0.0
    last_request: float = 0.0


def parse_ratelimit(headers: dict[str, str]) -> tuple[str | None, int | None, int | None,
                                                       int | None, int | None]:
    """Returns (bucket name, r, t, q, w) from RateLimit / RateLimit-Policy headers."""
    name = r = t = q = w = None
    m = _RL_RE.search(headers.get("ratelimit", ""))
    if m:
        name, r, t = m.group(1), int(m.group(2)), int(m.group(3))
    p = _POLICY_RE.search(headers.get("ratelimit-policy", ""))
    if p:
        name = name or p.group(1)
        q, w = int(p.group(2)), int(p.group(3))
    return name, r, t, q, w


def bucket_for(url: str) -> str:
    """Best guess of the server-side bucket before the first response names it."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if host == "huggingface.co":
        if "/resolve/" in parts.path or parts.path.startswith("/api/resolve-cache"):
            return f"{host}:resolvers"
        if parts.path.startswith("/api/"):
            return f"{host}:api"
        return f"{host}:pages"
    return host


class RateLimiter:
    def __init__(self, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 min_interval: dict[str, float] | None = None):
        self.sleep = sleep
        self.clock = clock
        self.buckets: dict[str, _Bucket] = {}
        # per-bucket minimum spacing, e.g. one request per second per non-API host
        self.min_interval = min_interval or {}
        self.default_host_interval = 0.0
        self.slept: list[float] = []
        # data files may be downloaded from several threads (checks.health.fetching); the
        # lock keeps the bucket state consistent, and a pause inside `before` holds it, so
        # spacing and rate-limit waits apply to all threads together
        self.lock = threading.RLock()

    def _bucket(self, key: str) -> _Bucket:
        return self.buckets.setdefault(key, _Bucket())

    def _pause(self, seconds: float) -> None:
        if seconds > 0:
            self.slept.append(seconds)
            self.sleep(seconds)

    def before(self, key: str) -> None:
        with self.lock:
            self._before(key)

    def _before(self, key: str) -> None:
        b = self._bucket(key)
        now = self.clock()
        spaced = ":" not in key and not (key == "hf.co" or key.endswith(HF_CDN_SUFFIX))
        interval = self.min_interval.get(key, self.default_host_interval if spaced else 0.0)
        if interval and b.last_request:
            wait = interval - (now - b.last_request)
            if wait > 0:
                self._pause(wait)
        if b.q and b.r is not None and b.t is not None and b.r < LOW_WATER * b.q:
            elapsed = self.clock() - b.seen_at
            remaining_t = max(0.0, b.t - elapsed)
            if remaining_t > 0:
                self._pause(remaining_t if b.r <= 0 else remaining_t / b.r)
        b.last_request = self.clock()

    def update(self, key: str, headers: dict[str, str]) -> None:
        with self.lock:
            self._update(key, headers)

    def _update(self, key: str, headers: dict[str, str]) -> None:
        name, r, t, q, w = parse_ratelimit(headers)
        if r is None and q is None:
            return
        b = self._bucket(key)
        if q is not None:
            b.q, b.w = q, w
        if r is not None:
            b.r, b.t = r, t
            b.seen_at = self.clock()
        if name and ":" in key:
            # keep the server's own bucket name in sync with our guess
            host = key.split(":", 1)[0]
            self.buckets[f"{host}:{name}"] = b

    def retry_after(self, key: str, headers: dict[str, str]) -> float:
        ra = headers.get("retry-after")
        if ra:
            try:
                return min(MAX_429_SLEEP, max(1.0, float(ra)))
            except ValueError:
                pass
        _, _, t, _, _ = parse_ratelimit(headers)
        return min(MAX_429_SLEEP, float(t) if t else 10.0)


def hf_token_present() -> bool:
    """True when the user is logged in (HF_TOKEN or `hf auth login`). The token is not kept."""
    try:
        from huggingface_hub import get_token
    except ImportError:  # pragma: no cover
        return False
    return get_token() is not None


def _hf_auth_headers() -> dict[str, str]:
    try:
        from huggingface_hub import get_token
    except ImportError:  # pragma: no cover
        return {}
    token = get_token()
    return {"authorization": f"Bearer {token}"} if token else {}


def _is_hf(url: str) -> bool:
    p = urlsplit(url)
    return p.scheme == "https" and (p.hostname or "") in HF_HOSTS


def classify_exception(exc: BaseException) -> str:
    """Map a transport exception to 'dns', 'timeout', 'connect' or 'protocol'."""
    if isinstance(exc, httpx2.TimeoutException):
        return "timeout"
    cur: BaseException | None = exc
    seen = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, socket.gaierror):
            if cur.errno in _nxdomain_errnos():
                return "dns"
            return "connect"
        cur = cur.__cause__ or cur.__context__
    msg = str(exc).lower()
    if "getaddrinfo failed" in msg or "name or service not known" in msg or \
            "nodename nor servname" in msg:
        return "dns"
    if isinstance(exc, httpx2.ConnectError | httpx2.NetworkError):
        return "connect"
    return "protocol"


def _nxdomain_errnos() -> set[int]:
    codes = {getattr(socket, "EAI_NONAME", -2)}
    if hasattr(socket, "EAI_NODATA"):
        codes.add(socket.EAI_NODATA)
    codes.add(11001)  # Windows WSAHOST_NOT_FOUND
    return codes


class Http:
    def __init__(self, cache_dir: Path | None = None, *, use_auth: bool = True,
                 transport: httpx2.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 timeout: float = 30.0, host_interval: float = 0.0):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.use_auth = use_auth
        self.sleep = sleep
        self.limiter = RateLimiter(sleep=sleep, clock=clock)
        self.limiter.default_host_interval = host_interval
        self.client = httpx2.Client(
            transport=transport, timeout=timeout, follow_redirects=False,
            headers={"user-agent": USER_AGENT},
        )
        self.network_calls = 0
        self._count_lock = threading.Lock()
        self._auth: dict[str, str] | None = None

    @property
    def authenticated(self) -> bool:
        return bool(self._auth_headers())

    def _auth_headers(self) -> dict[str, str]:
        if not self.use_auth:
            return {}
        if self._auth is None:
            self._auth = _hf_auth_headers()
        return self._auth

    # -- cache ---------------------------------------------------------------------------
    def _cache_paths(self, method: str, url: str, authed: bool) -> tuple[Path, Path] | None:
        if not self.cache_dir:
            return None
        key = hashlib.sha256(f"{method} {url} auth={authed}".encode()).hexdigest()
        d = self.cache_dir / "http" / key[:2]
        return d / f"{key}.json", d / f"{key}.bin"

    def _cache_get(self, method: str, url: str, authed: bool, ttl: float) -> Response | None:
        paths = self._cache_paths(method, url, authed)
        if not paths or not paths[0].exists():
            return None
        meta = json.loads(paths[0].read_text("utf-8"))
        if ttl != float("inf") and time.time() - meta["stored"] > ttl:
            return None
        return Response(status=meta["status"], url=meta["url"], headers=meta["headers"],
                        content=paths[1].read_bytes(), fetched_at=meta["fetched_at"],
                        history=[tuple(h) for h in meta["history"]], from_cache=True)

    def _cache_put(self, method: str, url: str, authed: bool, resp: Response) -> None:
        paths = self._cache_paths(method, url, authed)
        if not paths or not resp.ok or resp.truncated:
            return
        paths[0].parent.mkdir(parents=True, exist_ok=True)
        keep = {k: v for k, v in resp.headers.items()
                if k in ("content-type", "etag", "x-repo-commit", "last-modified")}
        paths[1].write_bytes(resp.content)
        paths[0].write_text(json.dumps({
            "status": resp.status, "url": resp.url, "headers": keep,
            "fetched_at": resp.fetched_at, "history": resp.history, "stored": time.time(),
        }), "utf-8")

    # -- requests ------------------------------------------------------------------------
    def _send_once(self, method: str, url: str, *, auth: bool, max_bytes: int | None,
                   timeout: float | None, params: dict[str, str] | None,
                   extra_headers: dict[str, str] | None = None) -> Response:
        key = bucket_for(url)
        headers = dict(self._auth_headers()) if (auth and _is_hf(url)) else {}
        headers.update(extra_headers or {})
        kwargs: dict[str, Any] = {"headers": headers, "params": params}
        if timeout is not None:
            kwargs["timeout"] = timeout
        tries_429 = 0
        while True:
            self.limiter.before(key)
            self._count()
            with self.client.stream(method, url, **kwargs) as r:
                hdrs = {k.lower(): v for k, v in r.headers.items()}
                self.limiter.update(key, hdrs)
                if r.status_code == 429 and tries_429 < MAX_429_RETRIES:
                    tries_429 += 1
                    wait = self.limiter.retry_after(key, hdrs)
                    log.info("429 from %s, sleeping %.0fs", urlsplit(url).hostname, wait)
                    self.limiter._pause(wait)
                    continue
                chunks: list[bytes] = []
                size = 0
                truncated = False
                if method != "HEAD":
                    for chunk in r.iter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if max_bytes is not None and size >= max_bytes:
                            truncated = True
                            break
                body = b"".join(chunks)
                if max_bytes is not None:
                    body = body[:max_bytes]
                return Response(status=r.status_code, url=str(r.url), headers=hdrs,
                                content=body, fetched_at=now_iso(), truncated=truncated)

    def request(self, method: str, url: str, *, auth: bool = True, ttl: float | None = None,
                max_bytes: int | None = None, retries: int = 3, timeout: float | None = None,
                params: dict[str, str] | None = None, max_redirects: int = MAX_REDIRECTS,
                headers: dict[str, str] | None = None) -> Response:
        """One logical request with manual redirects, retries and an optional cache.

        ttl: None = never cache; float('inf') = cache forever (revision-pinned URLs).
        headers: extra request headers for this host only (never followed across a redirect to
        another host, and never cached or logged).
        Raises FetchError for network failures after retries and for redirect loops.
        """
        if params:
            url = str(httpx2.URL(url, params=params))
        authed = bool(auth and self._auth_headers())
        if method == "GET" and ttl is not None:
            hit = self._cache_get(method, url, authed, ttl)
            if hit is not None:
                return hit
        history: list[tuple[int, str]] = []
        current = url
        seen = {url}
        while True:
            same_host = urlsplit(current).hostname == urlsplit(url).hostname
            resp = self._with_retries(method, current, auth=auth, max_bytes=max_bytes,
                                      retries=retries, timeout=timeout,
                                      headers=headers if same_host else None)
            if resp.status in (301, 302, 303, 307, 308) and "location" in resp.headers:
                history.append((resp.status, current))
                nxt = urljoin(current, resp.headers["location"])
                if nxt in seen:
                    raise FetchError("redirect-loop", f"redirect loop at {nxt}", url)
                if len(history) > max_redirects:
                    raise FetchError("too-many-redirects", f"more than {max_redirects}", url)
                seen.add(nxt)
                if resp.status == 303:
                    method = "GET"
                current = nxt
                continue
            resp.history = history
            if method == "GET" and ttl is not None:
                self._cache_put(method, url, authed, resp)
            return resp

    def _with_retries(self, method: str, url: str, *, auth: bool, max_bytes: int | None,
                      retries: int, timeout: float | None,
                      headers: dict[str, str] | None = None) -> Response:
        attempt = 0
        while True:
            try:
                resp = self._send_once(method, url, auth=auth, max_bytes=max_bytes,
                                       timeout=timeout, params=None, extra_headers=headers)
            except httpx2.HTTPError as exc:
                kind = classify_exception(exc)
                if kind == "dns" or attempt >= retries:
                    raise FetchError(kind, type(exc).__name__, url) from exc
            else:
                if resp.status < 500 or attempt >= retries:
                    return resp
            attempt += 1
            self.limiter._pause(min(30.0, 2 ** (attempt - 1)) + random.random() * 0.25)

    def get(self, url: str, **kw: Any) -> Response:
        return self.request("GET", url, **kw)

    def get_json(self, url: str, **kw: Any) -> Any:
        return self.request("GET", url, **kw).json()

    def _count(self) -> None:
        with self._count_lock:
            self.network_calls += 1

    def download(self, url: str, dest: Path, *, auth: bool = True, retries: int = 3) -> int:
        """Stream a file to `dest` (redirects handled by hand). Returns bytes written."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            attempt = 0
            while True:
                key = bucket_for(current)
                headers = dict(self._auth_headers()) if (auth and _is_hf(current)) else {}
                self.limiter.before(key)
                self._count()
                try:
                    with self.client.stream("GET", current, headers=headers,
                                            timeout=httpx2.Timeout(60.0, read=120.0)) as r:
                        hdrs = {k.lower(): v for k, v in r.headers.items()}
                        self.limiter.update(key, hdrs)
                        if r.status_code in (301, 302, 303, 307, 308):
                            current = urljoin(current, hdrs["location"])
                            break
                        if r.status_code == 429 or r.status_code >= 500:
                            if attempt >= retries:
                                raise FetchError("http", f"HTTP {r.status_code}", url)
                            attempt += 1
                            wait = (self.limiter.retry_after(key, hdrs)
                                    if r.status_code == 429 else 2 ** attempt)
                            self.limiter._pause(wait)
                            continue
                        if r.status_code != 200:
                            raise FetchError("http", f"HTTP {r.status_code}", url)
                        n = 0
                        with open(dest, "wb") as fh:
                            for chunk in r.iter_bytes(1 << 20):
                                fh.write(chunk)
                                n += len(chunk)
                        return n
                except httpx2.HTTPError as exc:
                    if attempt >= retries:
                        raise FetchError(classify_exception(exc), type(exc).__name__,
                                         url) from exc
                    attempt += 1
                    self.limiter._pause(2 ** attempt)
        raise FetchError("too-many-redirects", f"more than {MAX_REDIRECTS}", url)

    def close(self) -> None:
        self.client.close()
