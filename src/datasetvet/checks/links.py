"""Link check (PLAN.md 5.4). Task 2.6.

HEAD, falling back to GET (first 64 KB only) when HEAD does not give a 2xx; up to 5 redirects;
15 s timeout; 2 retries with backoff; one request per host per second; robots.txt obeyed for
non-Hugging Face hosts. Links never carry the user's token.

| status      | rule                                                              |
|-------------|-------------------------------------------------------------------|
| ok          | final response 2xx                                                |
| dead        | 404 or 410, or DNS NXDOMAIN; a configs data_files path that matches no repo file |
| restricted  | 401, 403, 451, or a gated Hugging Face dataset                    |
| unreachable | timeout / connection error after retries, or 5xx after retries    |
| unknown     | 429 that did not clear, redirect loops, robots.txt disallows, other codes |
"""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from datasetvet.config import Settings
from datasetvet.http import HF_HOSTS, FetchError, Http
from datasetvet.hubs.base import LinkRef
from datasetvet.model import CheckResult, Evidence, Fact, Family, LinkStatus, now_iso

GET_CAP = 64 * 1024
ROBOTS_AGENT = "datasetvet"
_HF_DATASET_RE = re.compile(r"^/datasets/([^/]+/[^/]+|[^/]+)/?$")


def status_for_code(code: int) -> LinkStatus:
    if 200 <= code < 300:
        return LinkStatus.OK
    if code in (404, 410):
        return LinkStatus.DEAD
    if code in (401, 403, 451):
        return LinkStatus.RESTRICTED
    if code >= 500:
        return LinkStatus.UNREACHABLE
    return LinkStatus.UNKNOWN


class LinkChecker:
    def __init__(self, http: Http, settings: Settings,
                 gated_lookup: Callable[[str], bool | str | None] | None = None):
        self.http = http
        self.settings = settings
        self.gated_lookup = gated_lookup
        self._robots: dict[str, RobotFileParser | None] = {}

    def _robots_for(self, url: str) -> RobotFileParser | None:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        rp: RobotFileParser | None = None
        try:
            resp = self.http.get(f"{origin}/robots.txt", auth=False, ttl=86400.0, retries=0,
                                 timeout=self.settings.link_timeout, max_bytes=512 * 1024)
            if resp.ok:
                rp = RobotFileParser()
                rp.parse(resp.text.splitlines())
        except FetchError:
            rp = None
        self._robots[origin] = rp
        return rp

    def check(self, link: LinkRef) -> CheckResult:
        url = link.url
        p = urlsplit(url)
        checked_at = now_iso()
        ev = [link.evidence] if link.evidence else []
        data: dict = {"url": url, "label": link.label, "checked_at": checked_at}

        def result(status: LinkStatus, text: str, **extra) -> CheckResult:
            data.update(extra)
            return CheckResult("links", Family.LINKS, status, link.label,
                               [Fact(text, ev + [Evidence(url=data.get("final_url", url),
                                                          fetched_at=checked_at)])], data)

        if p.scheme not in ("http", "https") or not p.hostname:
            return result(LinkStatus.UNKNOWN, f"{url}: not an http(s) URL; not checked.")
        host = p.hostname
        if host not in HF_HOSTS:
            rp = self._robots_for(url)
            if rp is not None and not rp.can_fetch(ROBOTS_AGENT, url):
                return result(LinkStatus.UNKNOWN,
                              f"{url}: not checked, the site's robots.txt disallows it.",
                              robots_disallowed=True)
        try:
            resp = self.http.request("HEAD", url, auth=False, retries=self.settings.link_retries,
                                     timeout=self.settings.link_timeout)
            method = "HEAD"
            if not resp.ok:
                resp = self.http.request("GET", url, auth=False, max_bytes=GET_CAP,
                                         retries=self.settings.link_retries,
                                         timeout=self.settings.link_timeout)
                method = "GET"
        except FetchError as exc:
            if exc.kind == "dns":
                return result(LinkStatus.DEAD, f"{url}: the host name does not resolve "
                              f"(NXDOMAIN), checked {checked_at}.", error=exc.kind)
            if exc.kind in ("redirect-loop", "too-many-redirects"):
                return result(LinkStatus.UNKNOWN, f"{url}: {exc.message}, checked "
                              f"{checked_at}.", error=exc.kind)
            return result(LinkStatus.UNREACHABLE, f"{url}: {exc.kind} error after "
                          f"{self.settings.link_retries} retries, checked {checked_at}.",
                          error=exc.kind)
        data.update(final_url=resp.url, code=resp.status, method=method,
                    redirects=len(resp.history))
        status = status_for_code(resp.status)
        where = f" (final URL {resp.url})" if resp.url != url else ""
        if status == LinkStatus.OK and host == "huggingface.co" and self.gated_lookup:
            m = _HF_DATASET_RE.match(urlsplit(resp.url).path)
            if m:
                gated = self.gated_lookup(m.group(1))
                if gated:
                    return result(LinkStatus.RESTRICTED,
                                  f"{url}: HTTP {resp.status}{where}, but the dataset is gated "
                                  f"({gated}): its files need the owner's terms accepted. "
                                  f"Checked {checked_at}.", gated=str(gated))
        if resp.status == 429:
            text = f"{url}: HTTP 429 (rate limited) did not clear after retries"
        else:
            text = f"{url}: HTTP {resp.status}{where}"
        return result(status, f"{text}, checked {checked_at}.")


def missing_file_result(pattern: str, config: str, evidence: Evidence | None) -> CheckResult:
    return CheckResult(
        "links", Family.LINKS, LinkStatus.DEAD, f"configs data_files ({config})",
        [Fact(f"Config {config}: data_files path {pattern!r} matches no file in the repo "
              "(missing file).", [evidence] if evidence else [])],
        {"url": None, "pattern": pattern, "config": config, "missing_file": True})


def check_links(links: list[LinkRef], checker: LinkChecker, max_links: int,
                progress: Callable[[str], None] | None = None,
                ) -> tuple[list[CheckResult], list[str]]:
    targets = [ln for ln in links if urlsplit(ln.url).scheme in ("http", "https")]
    not_checked = []
    if len(targets) > max_links:
        not_checked.append(f"{len(targets) - max_links} links beyond --max-links {max_links}")
        targets = targets[:max_links]
    out = []
    for i, ln in enumerate(targets, 1):
        if progress:
            progress(f"link {i}/{len(targets)}: {ln.url}")
        out.append(checker.check(ln))
    return out, not_checked
