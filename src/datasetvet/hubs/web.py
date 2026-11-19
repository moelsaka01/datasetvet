"""Plain-URL source resolver (task 3.5).

- A licence's own URL (creativecommons.org/licenses/by/4.0/, opensource.org/licenses/MIT, the
  SPDX list's `seeAlso` URLs) is a structured claim: the URL names the licence, nothing is
  fetched.
- A page whose URL path looks like a licence or terms page (license, licence, terms, copyright,
  legal) is fetched (first 512 KB), HTML is reduced to text, and the scanner reads it.
- Any other URL (a paper, a homepage) is not read for a licence.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from datasetvet.http import FetchError, Http
from datasetvet.hubs.base import LicenceClaim, SourceRead, TextBlob
from datasetvet.licences.matcher import licence_for_url
from datasetvet.model import Evidence

MAX_PAGE_BYTES = 512 * 1024
_LICENCE_PATH_RE = re.compile(r"licen[cs]e|terms|copyright|legal|/tos\b|terms[-_]of[-_]use",
                              re.IGNORECASE)


class _Text(HTMLParser):
    SKIP = frozenset({"script", "style", "noscript", "svg", "head"})
    BLOCK = frozenset({"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
                       "section", "article", "pre", "td", "th", "dd", "dt", "blockquote"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    text = "".join(p.parts)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def short_label(url: str) -> str:
    p = urlsplit(url)
    host = (p.hostname or "").removeprefix("www.")
    return (host + p.path.rstrip("/"))[:80]


class WebResolver:
    name = "web"

    def __init__(self, http: Http):
        self.http = http

    def matches(self, url: str) -> bool:
        return urlsplit(url).scheme in ("http", "https")

    @staticmethod
    def is_licence_page(url: str) -> bool:
        return bool(_LICENCE_PATH_RE.search(urlsplit(url).path or ""))

    def read(self, url: str) -> SourceRead:
        label = short_label(url)
        lid = licence_for_url(url)
        if lid:
            ev = Evidence(url=url, note="the URL is this licence's own URL; not fetched")
            return SourceRead(url, label, "licence URL", "read",
                              claims=[LicenceClaim("licence URL", lid, ev)])
        if not self.is_licence_page(url):
            return SourceRead(url, label, "web page", "skipped",
                              note="not a licence or terms page by its URL, so not read")
        try:
            resp = self.http.get(url, auth=False, max_bytes=MAX_PAGE_BYTES, ttl=3600.0)
        except FetchError as exc:
            return SourceRead(url, label, "web page", "unreadable",
                              note=f"fetch failed ({exc.kind})")
        if not resp.ok:
            return SourceRead(url, label, "web page", "unreadable",
                              note=f"HTTP {resp.status}")
        ctype = resp.headers.get("content-type", "").lower()
        if "html" in ctype:
            text = html_to_text(resp.text)
        elif ctype.startswith("text/") or not ctype:
            text = resp.text
        else:
            return SourceRead(url, label, "web page", "unreadable",
                              note=f"not a text page ({ctype.split(';')[0]})")
        ev = Evidence(url=resp.url, fetched_at=resp.fetched_at,
                      note="web page: not pinned to a revision")
        return SourceRead(url, label, "web page", "read",
                          texts=[TextBlob(path=label, text=text, truncated=resp.truncated,
                                          evidence=ev)])
