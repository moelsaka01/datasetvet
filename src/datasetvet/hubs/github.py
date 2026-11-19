"""GitHub source resolver: the licence files of a stated GitHub repository. Task 3.5.

Anonymous path (default), zero `api.github.com` calls:
1. pin the repository's HEAD to a commit sha with git's smart-HTTP ref advertisement
   (`github.com/{o}/{r}.git/info/refs?service=git-upload-pack`; not API rate-limited);
2. read licence files at that sha from `raw.githubusercontent.com`, trying the common root
   names in `ROOT_NAMES` (first hit only) and the data-licence names in `DATA_NAMES`.
Without a token, "no file under these names" is reported as such, not as "no licence".

Token path, only when `GITHUB_TOKEN` is set in the user's environment: also
`GET api.github.com/repos/{o}/{r}/license`, which is GitHub's own detection (licensee). It is
labelled as GitHub's, never as ours. The token is sent only to api.github.com and never
logged, cached or reported.
"""

from __future__ import annotations

import os
import re
from urllib.parse import quote, urlsplit

from datasetvet.http import FetchError, Http
from datasetvet.hubs.base import LicenceClaim, SourceRead, TextBlob
from datasetvet.model import Evidence

ROOT_NAMES = ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"]
DATA_NAMES = ["DATA_LICENSE", "LICENSE-DATA"]
MAX_LICENCE_BYTES = 512 * 1024
_REPO_RE = re.compile(r"^/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]+?)(?:\.git)?(?:/|$)")
_NOT_OWNERS = {"orgs", "topics", "features", "about", "sponsors", "settings", "marketplace",
               "search", "collections", "apps", "login", "join", "explore", "pricing",
               "security", "enterprise", "site", "customer-stories", "readme", "trending"}
_HEAD_RE = re.compile(rb"([0-9a-f]{40}) HEAD\x00")


def parse_repo(url: str) -> tuple[str, str] | None:
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or (p.hostname or "").lower() not in (
            "github.com", "www.github.com"):
        return None
    m = _REPO_RE.match(p.path)
    if not m or m.group(1).lower() in _NOT_OWNERS:
        return None
    return m.group(1), m.group(2)


class GitHubResolver:
    name = "github"

    def __init__(self, http: Http, token: str | None = None):
        self.http = http
        self.token = token if token is not None else (os.environ.get("GITHUB_TOKEN") or None)

    @property
    def authenticated(self) -> bool:
        return bool(self.token)

    def matches(self, url: str) -> bool:
        return parse_repo(url) is not None

    def head_sha(self, owner: str, repo: str) -> tuple[str | None, str, str, int]:
        """(sha or None, owner, repo, HTTP status), following a rename redirect."""
        url = f"https://github.com/{owner}/{repo}.git/info/refs"
        resp = self.http.get(url, params={"service": "git-upload-pack"}, max_bytes=65536,
                             auth=False)
        moved = parse_repo(resp.url.replace(".git/info/refs", "")) if resp.url else None
        if moved:
            owner, repo = moved
        m = _HEAD_RE.search(resp.content) if resp.ok else None
        return (m.group(1).decode() if m else None), owner, repo, resp.status

    def read(self, url: str) -> SourceRead:
        parsed = parse_repo(url)
        assert parsed is not None
        owner, repo = parsed
        label = f"github.com/{owner}/{repo}"
        try:
            sha, owner, repo, status = self.head_sha(owner, repo)
        except FetchError as exc:
            return SourceRead(url, label, "github", "unreadable",
                              note=f"could not reach GitHub ({exc.kind})")
        label = f"github.com/{owner}/{repo}"
        if sha is None:
            why = ("repository not found or private" if status in (401, 403, 404)
                   else f"no HEAD commit in the ref advertisement (HTTP {status})")
            return SourceRead(url, label, "github", "unreadable", note=f"{why} (HTTP {status})")
        out = SourceRead(url, label, "github", "read", revision=sha)
        for names, first_only in ((ROOT_NAMES, True), (DATA_NAMES, False)):
            for name in names:
                out.names_tried.append(name)
                blob = self._raw(owner, repo, sha, name)
                if blob is not None:
                    out.texts.append(blob)
                    if first_only:
                        break
        if self.token:
            claim, none = self._api_licence(owner, repo, sha)
            if claim:
                out.claims.append(claim)
            out.confirmed_none = none and not out.texts
        if not out.texts and not out.claims:
            out.state = "no licence file"
            tried = ", ".join(out.names_tried)
            out.note = (f"no file named {tried} at the repository root"
                        + ("; GitHub's API also reports no licence" if out.confirmed_none else
                           "; other file names are not checked without GITHUB_TOKEN"))
        return out

    def _raw(self, owner: str, repo: str, sha: str, name: str) -> TextBlob | None:
        raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{sha}/{quote(name)}"
        try:
            resp = self.http.get(raw, ttl=float("inf"), max_bytes=MAX_LICENCE_BYTES, auth=False)
        except FetchError:
            return None
        if not resp.ok:
            return None
        ev = Evidence(url=f"https://github.com/{owner}/{repo}/blob/{sha}/{quote(name)}",
                      revision=sha, path=name, fetched_at=resp.fetched_at)
        return TextBlob(path=name, text=resp.text, truncated=resp.truncated, evidence=ev)

    def _api_licence(self, owner: str, repo: str, sha: str) -> tuple[LicenceClaim | None, bool]:
        api = f"https://api.github.com/repos/{owner}/{repo}/license"
        try:
            resp = self.http.get(api, auth=False, headers={
                "authorization": f"Bearer {self.token}",
                "accept": "application/vnd.github+json"})
        except FetchError:
            return None, False
        if resp.status == 404:
            return None, True
        if not resp.ok:
            return None, False
        data = resp.json()
        spdx_id = ((data.get("license") or {}).get("spdx_id")) or "NOASSERTION"
        ev = Evidence(url=data.get("html_url"), revision=sha, path=data.get("path"),
                      fetched_at=resp.fetched_at,
                      note="GitHub's API reports the default branch; its sha may differ")
        return LicenceClaim("GitHub's detection (licensee)", spdx_id, ev), False
