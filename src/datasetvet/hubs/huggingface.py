"""Hugging Face adapter (v1). Task 2.4.

Endpoints (all free; anonymous works, a `hf auth login` token raises the rate limits):
- GET /api/datasets/{id}[/revision/{rev}]?blobs=true  -> sha, gated, cardData, siblings, tags
- GET /datasets/{id}/resolve/{sha}/README.md            -> the card, pinned to the sha
- GET /api/datasets/{id}/refs                           -> commit of refs/convert/parquet
- GET datasets-server /parquet and /size                -> Parquet files, partial flag, rows
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import yaml

from datasetvet.http import FetchError, Http
from datasetvet.hubs.base import (
    Card,
    DataPlan,
    GitPlan,
    LicenceClaim,
    LinkRef,
    ParentRef,
    RepoFile,
    SplitFile,
    SplitSource,
    TextBlob,
    local_name,
)
from datasetvet.model import DatasetRef, Evidence

HUB = "https://huggingface.co"
VIEWER = "https://datasets-server.huggingface.co"
FOREVER = float("inf")
MAX_BLOB = 10 * 1024 * 1024  # the Hub keeps larger files in LFS, which git does not serve
LISTING_CAP = 100_000  # the Hub's file listing seen to stop at exactly this many entries

_SHA_RE = re.compile(r"[0-9a-f]{40}")
_ID_RE = re.compile(r"^[A-Za-z0-9][\w.-]*(/[A-Za-z0-9][\w.-]*)?$")
_URL_RE = re.compile(r"https?://[^\s<>\"'\)\]\}`|]+", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[([^\]]{1,60})\]\((https?://[^\s)]+)\)")
_BULLET_RE = re.compile(r"^\s*[-*+]\s*\*\*([^*]+?)\*\*\s*:?\s*(.*)$")
STATED_LABELS = ("homepage", "repository", "repo", "paper", "point of contact", "source",
                 "website", "code", "download", "data", "project page", "github")
SPLIT_WORDS = {
    "train": ("train", "training"),
    "validation": ("validation", "valid", "val", "dev"),
    "test": ("test", "testing", "eval", "evaluation"),
}
SUPPORTED_EXT = {".parquet": "parquet", ".csv": "csv", ".tsv": "tsv", ".jsonl": "jsonl",
                 ".json": "json", ".ndjson": "jsonl"}


class DatasetNotFound(LookupError):
    pass


def file_format(path: str) -> str | None:
    p = path.lower()
    if p.endswith(".gz"):
        p = p[:-3]
        fmt = SUPPORTED_EXT.get(Path(p).suffix)
        return fmt if fmt in ("csv", "tsv", "jsonl", "json") else None
    return SUPPORTED_EXT.get(Path(p).suffix)


def split_front_matter(text: str) -> tuple[str | None, str, int]:
    """Returns (yaml text or None, body, number of lines before the body)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text, 0
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return "".join(lines[1:i]), "".join(lines[i + 1:]), i + 1
    return None, text, 0


def _key_lines(yaml_text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for n, line in enumerate(yaml_text.splitlines(), start=2):  # line 1 is '---'
        m = re.match(r"^([A-Za-z0-9_][\w-]*)\s*:", line)
        if m and m.group(1) not in out:
            out[m.group(1)] = n
    return out


class HuggingFaceAdapter:
    name = "huggingface"

    def __init__(self, http: Http):
        self.http = http
        self._info: dict[tuple[str, str], dict[str, Any]] = {}

    # -- refs ----------------------------------------------------------------------------
    def matches(self, ref: str) -> bool:
        return self._parse(ref) is not None

    @staticmethod
    def _parse(ref: str) -> tuple[str, str | None] | None:
        ref = ref.strip()
        rev: str | None = None
        if ref.startswith("hf:"):
            body = ref[3:]
            body = body.removeprefix("datasets/")
            if "@" in body:
                body, rev = body.split("@", 1)
            return (body, rev or None) if _ID_RE.match(body) else None
        p = urlsplit(ref)
        if p.scheme in ("http", "https") and p.hostname in ("huggingface.co",
                                                            "www.huggingface.co"):
            parts = [x for x in p.path.split("/") if x]
            if len(parts) >= 3 and parts[0] == "datasets":
                ds_id = "/".join(parts[1:3])
                if len(parts) >= 5 and parts[3] in ("tree", "blob", "resolve"):
                    rev = unquote(parts[4])
                return (ds_id, rev) if _ID_RE.match(ds_id) else None
            if len(parts) == 2 and parts[0] == "datasets" and _ID_RE.match(parts[1]):
                return parts[1], None
        return None

    def resolve(self, ref: str) -> DatasetRef:
        parsed = self._parse(ref)
        if parsed is None:
            raise ValueError(f"not a Hugging Face dataset reference: {ref!r}")
        ds_id, rev = parsed
        url = f"{HUB}/api/datasets/{ds_id}"
        if rev:
            url += f"/revision/{quote(rev, safe='')}"
        resp = self.http.get(url, params={"blobs": "true"})
        if resp.status in (401, 403, 404):
            raise DatasetNotFound(
                f"{ds_id}{'@' + rev if rev else ''}: not found on the Hugging Face Hub, "
                f"or private and not readable with your login (HTTP {resp.status})")
        if not resp.ok:
            raise FetchError("http", f"HTTP {resp.status} from the Hub API", url)
        info = resp.json()
        sha = info["sha"]
        canonical = info.get("id", ds_id)
        self._info[(canonical, sha)] = info
        return DatasetRef(
            hub=self.name, id=canonical, revision=sha, requested=ref, requested_revision=rev,
            url=f"{HUB}/datasets/{canonical}/tree/{sha}", gated=info.get("gated", False),
            private=bool(info.get("private")), disabled=bool(info.get("disabled")),
        )

    def info(self, ds: DatasetRef) -> dict[str, Any]:
        key = (ds.id, ds.revision)
        if key not in self._info:
            url = f"{HUB}/api/datasets/{ds.id}/revision/{ds.revision}"
            self._info[key] = self.http.get_json(url, params={"blobs": "true"}, ttl=FOREVER)
        return self._info[key]

    def _resolve_url(self, ds: DatasetRef, path: str, rev: str | None = None) -> str:
        return f"{HUB}/datasets/{ds.id}/resolve/{rev or ds.revision}/{quote(path)}"

    def blob_url(self, ds: DatasetRef, path: str, line: int | None = None) -> str:
        u = f"{HUB}/datasets/{ds.id}/blob/{ds.revision}/{quote(path)}"
        return f"{u}#L{line}" if line else u

    # -- card ----------------------------------------------------------------------------
    def card(self, ds: DatasetRef) -> Card:
        info = self.info(ds)
        tags = list(info.get("tags") or [])
        has_readme = any(s.get("rfilename") == "README.md" for s in info.get("siblings", []))
        ev = Evidence(url=self.blob_url(ds, "README.md"), revision=ds.revision,
                      path="README.md")
        if not has_readme:
            ev.note = "no README.md at this revision"
            return Card(text=None, metadata={}, body="", evidence=ev, tags=tags)
        resp = self.http.get(self._resolve_url(ds, "README.md"), ttl=FOREVER)
        ev.fetched_at = resp.fetched_at
        if resp.status in (401, 403):
            ev.note = ("README.md is not readable without accepting this dataset's terms; "
                       "metadata taken from the Hub API's cardData instead")
            meta = info.get("cardData") or {}
            return Card(text=None, metadata=meta, body="", evidence=ev, tags=tags)
        if not resp.ok:
            ev.note = f"README.md fetch failed (HTTP {resp.status})"
            return Card(text=None, metadata=info.get("cardData") or {}, body="", evidence=ev,
                        tags=tags)
        return parse_card(resp.text, ev, tags)

    def files(self, ds: DatasetRef) -> list[RepoFile]:
        return [RepoFile(s["rfilename"], s.get("size")) for s in self.info(ds).get("siblings",
                                                                                   [])]

    def read_text(self, ds: DatasetRef, path: str, max_bytes: int) -> TextBlob:
        resp = self.http.get(self._resolve_url(ds, path), ttl=FOREVER, max_bytes=max_bytes)
        ev = Evidence(url=self.blob_url(ds, path), revision=ds.revision, path=path,
                      fetched_at=resp.fetched_at)
        if not resp.ok:
            raise FetchError("http", f"HTTP {resp.status}", path)
        return TextBlob(path=path, text=resp.text, truncated=resp.truncated, evidence=ev)

    def native_licences(self, ds: DatasetRef) -> list[LicenceClaim]:
        meta = (self.info(ds).get("cardData") or {})
        raw = meta.get("license")
        values = raw if isinstance(raw, list) else ([raw] if raw else [])
        ev = Evidence(url=self.blob_url(ds, "README.md"), revision=ds.revision,
                      path="README.md")
        return [LicenceClaim("card field", str(v), ev) for v in values]

    def stated_sources(self, card: Card) -> list[LinkRef]:
        return extract_links(card)

    def parents(self, card: Card) -> list[ParentRef]:
        return parent_refs(card.metadata.get("source_datasets"))

    # -- data ----------------------------------------------------------------------------
    def splits(self, ds: DatasetRef, card: Card | None = None) -> DataPlan:
        card = card or self.card(ds)
        notes: list[str] = []
        pq = self.http.get(f"{VIEWER}/parquet", params={"dataset": ds.id})
        if pq.status in (401, 403) and ds.gated:
            return DataPlan([], not_checked=(
                f"gated dataset ({ds.gated}): the data needs this dataset's terms accepted by "
                "your Hugging Face account, and datasetvet never accepts terms for you"))
        conv: dict[str, Any] | None = pq.json() if pq.ok else None
        if conv and conv.get("parquet_files") and not conv.get("partial"):
            if conv.get("pending") or conv.get("failed"):
                notes.append("the Parquet conversion lists pending or failed configs; "
                             "only converted files were read")
            plan = self._conversion_plan(ds, card, conv)
            plan.notes = notes + plan.notes
            return plan
        if conv and conv.get("partial"):
            notes.append("HF's Parquet conversion is partial (it stops after the first ~5 GB "
                         "per split), so the original files are used instead")
        elif not pq.ok:
            reason = _error_text(pq)
            notes.append(f"no Parquet conversion from the Dataset Viewer (HTTP {pq.status}"
                         f"{': ' + reason if reason else ''}); trying the original files")
        disabled = pq.status == 501 and "disabled" in _error_text(pq)
        if disabled and not card.metadata.get("configs"):
            return DataPlan([], notes=notes, not_checked=(
                "the owner disabled the Dataset Viewer and the card has no `configs`, so "
                "nothing states which files are data (the Dataset Viewer is disabled)"))
        plan = self._original_plan(ds, card)
        plan.notes = notes + plan.notes
        return plan

    def _convert_sha(self, ds: DatasetRef) -> str | None:
        resp = self.http.get(f"{HUB}/api/datasets/{ds.id}/refs")
        if not resp.ok:
            return None
        for c in resp.json().get("converts", []):
            if c.get("ref") == "refs/convert/parquet":
                return c.get("targetCommit")
        return None

    def _conversion_plan(self, ds: DatasetRef, card: Card, conv: dict[str, Any]) -> DataPlan:
        sha = self._convert_sha(ds)
        size = self.http.get(f"{VIEWER}/size", params={"dataset": ds.id})
        rows: dict[tuple[str, str], tuple[int | None, int | None]] = {}
        if size.ok:
            for s in size.json().get("size", {}).get("splits", []):
                rows[(s["config"], s["split"])] = (s.get("num_rows"),
                                                   s.get("num_bytes_parquet_files"))
        grouped: dict[tuple[str, str], list[SplitFile]] = {}
        for f in conv["parquet_files"]:
            url = f["url"]
            if sha:
                url = url.replace("/resolve/refs%2Fconvert%2Fparquet/", f"/resolve/{sha}/")
            path = unquote(url.split("/resolve/", 1)[1].split("/", 1)[1])
            grouped.setdefault((f["config"], f["split"]), []).append(
                SplitFile(url=url, path=path, size=f.get("size"), fmt="parquet"))
        labels = card_label_features(card.metadata)
        splits = []
        for (config, split), files in sorted(grouped.items()):
            files.sort(key=lambda x: x.path)
            n_rows, n_bytes = rows.get((config, split), (None, None))
            if n_bytes is None:
                n_bytes = sum(f.size or 0 for f in files)
            lab = labels.get(config, labels.get("*", {}))
            splits.append(SplitSource(
                config=config, split=split, files=files, rows=n_rows, bytes=n_bytes,
                source="parquet conversion", revision=sha,
                label_columns=list(lab), label_names=lab))
        notes = []
        if not sha:
            notes.append("could not pin the Parquet conversion to a commit")
        return DataPlan(splits, notes=notes)

    def _original_plan(self, ds: DatasetRef, card: Card) -> DataPlan:
        # hidden files and folders (.gitattributes, .metadata/...) are never data
        files = [f for f in self.files(ds) if f.path != "README.md"
                 and not any(part.startswith(".") for part in f.path.split("/"))]
        supported = [f for f in files if file_format(f.path)]
        if not supported:
            exts = sorted({Path(f.path).suffix.lower() or "(none)" for f in files})[:12]
            return DataPlan([], not_checked=(
                "unsupported format: no Parquet conversion and no Parquet, CSV or JSON Lines "
                f"files in the repo (file types: {', '.join(exts) or 'none'})"))
        mapping = map_data_files(card.metadata.get("configs"), [f.path for f in supported])
        by_path = {f.path: f for f in supported}
        info_rows = card_split_rows(card.metadata)
        labels = card_label_features(card.metadata)
        splits = []
        for (config, split), paths in sorted(mapping.items()):
            sfiles = [SplitFile(url=self._resolve_url(ds, p), path=p, size=by_path[p].size,
                                fmt=file_format(p) or "") for p in sorted(paths)]
            lab = labels.get(config, labels.get("*", {}))
            splits.append(SplitSource(
                config=config, split=split, files=sfiles, rows=info_rows.get((config, split)),
                bytes=sum(f.size or 0 for f in sfiles), source="original files",
                revision=ds.revision, label_columns=list(lab), label_names=lab))
        if not splits:
            return DataPlan([], not_checked="no data files matched the card's configs")
        return DataPlan(splits, git=self._git_plan(ds, splits))

    def _git_plan(self, ds: DatasetRef, splits: list[SplitSource]) -> GitPlan | None:
        """The data files git can serve (not in LFS, at most MAX_BLOB), with their blob ids
        as the Hub lists them, and an upper bound of what one filtered fetch downloads."""
        if not (ds.revision and _SHA_RE.fullmatch(ds.revision)):
            return None
        siblings = self.info(ds).get("siblings", [])
        if len(siblings) >= LISTING_CAP:
            return None  # the listing may be cut off, so the fetch size cannot be bounded
        small = {s["rfilename"]: s for s in siblings
                 if not s.get("lfs") and s.get("blobId") and s.get("size") is not None
                 and s["size"] <= MAX_BLOB}
        wanted = {f.path for s in splits for f in s.files}
        blob_ids = {p: small[p]["blobId"] for p in wanted if p in small}
        # every small blob comes with the fetch, plus LFS pointers and trees (~100-200 bytes)
        estimate = (sum(s["size"] for s in small.values())
                    + 200 * (len(siblings) - len(small)) + 100 * len(siblings))
        return GitPlan(url=f"{HUB}/datasets/{ds.id}", sha=ds.revision, blob_ids=blob_ids,
                       pack_estimate=estimate, max_blob=MAX_BLOB)

    def fetch(self, f: SplitFile, dest_dir: Path) -> Path:
        dest = Path(dest_dir) / local_name(f.path)
        self.http.download(f.url, dest)
        return dest


def parent_refs(raw: Any) -> list[ParentRef]:
    """Declared parents from a `source_datasets` value (PLAN.md 5.3). `original` is no parent;
    `extended|other-...` and free text are kept with only their raw value (unresolvable)."""
    vals = raw if isinstance(raw, list) else ([raw] if raw else [])
    out = []
    for v in map(str, vals):
        s = v.strip()
        if not s or s.lower() == "original":
            continue
        target = s.split("|", 1)[1].strip() if s.lower().startswith("extended|") else s
        if not target or target.lower() == "extended" or target.lower().startswith("other"):
            out.append(ParentRef(raw=s))
        elif target.startswith(("http://", "https://")):
            out.append(ParentRef(raw=s, url=target))
        elif _ID_RE.match(target):
            out.append(ParentRef(raw=s, hub="huggingface", id=target))
        else:
            out.append(ParentRef(raw=s))
    return out


def _error_text(resp: Any) -> str:
    try:
        return str(resp.json().get("error", ""))[:160]
    except (ValueError, AttributeError):
        return ""


def parse_card(text: str, evidence: Evidence, tags: list[str] | None = None) -> Card:
    yaml_text, body, offset = split_front_matter(text)
    meta: dict[str, Any] = {}
    err = None
    if yaml_text is not None:
        try:
            loaded = yaml.safe_load(yaml_text)
            if isinstance(loaded, dict):
                meta = loaded
            elif loaded is not None:
                err = "YAML front matter is not a mapping"
        except yaml.YAMLError as exc:
            err = f"YAML front matter does not parse: {str(exc).splitlines()[0]}"
    return Card(text=text, metadata=meta, body=body, evidence=evidence,
                key_lines=_key_lines(yaml_text) if yaml_text else {}, body_offset=offset,
                yaml_error=err, tags=list(tags or []))


def card_label_features(meta: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """config -> {label column: class names} from dataset_info ClassLabel features.
    A config of '*' means dataset_info had no config_name."""
    info = meta.get("dataset_info")
    infos = info if isinstance(info, list) else ([info] if isinstance(info, dict) else [])
    out: dict[str, dict[str, list[str]]] = {}
    for item in infos:
        if not isinstance(item, dict):
            continue
        config = item.get("config_name", "*")
        feats = item.get("features") or []
        found: dict[str, list[str]] = {}
        for feat in feats if isinstance(feats, list) else []:
            if not isinstance(feat, dict):
                continue
            names = _class_label_names(feat.get("dtype"))
            if names is None and isinstance(feat.get("sequence"), dict):
                names = _class_label_names(feat["sequence"])
            if names is None and isinstance(feat.get("list"), dict):
                names = _class_label_names(feat["list"])
            if names is not None:
                found[feat.get("name", "")] = names
        out[config] = found
    return out


def _class_label_names(dtype: Any) -> list[str] | None:
    if isinstance(dtype, dict) and "class_label" in dtype:
        names = (dtype["class_label"] or {}).get("names") or {}
        if isinstance(names, dict):
            return [str(names[k]) for k in sorted(names, key=lambda x: int(x))]
        return [str(n) for n in names]
    return None


def card_split_rows(meta: dict[str, Any]) -> dict[tuple[str, str], int]:
    info = meta.get("dataset_info")
    infos = info if isinstance(info, list) else ([info] if isinstance(info, dict) else [])
    out = {}
    for item in infos:
        if not isinstance(item, dict):
            continue
        config = item.get("config_name", "default")
        for s in item.get("splits") or []:
            if isinstance(s, dict) and "name" in s and "num_examples" in s:
                out[(config, s["name"])] = int(s["num_examples"])
    return out


def _glob_match(path: str, pattern: str) -> bool:
    pattern = pattern.lstrip("./")
    return fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(path, pattern.replace(
        "**/", ""))


def map_data_files(configs: Any, paths: list[str]) -> dict[tuple[str, str], list[str]]:
    """(config, split) -> repo paths, from the card's `configs` or HF's file-name convention."""
    out: dict[tuple[str, str], list[str]] = {}
    if isinstance(configs, list) and configs:
        for cfg in configs:
            if not isinstance(cfg, dict):
                continue
            name = str(cfg.get("config_name", "default"))
            for split, patterns in _data_file_patterns(cfg.get("data_files")):
                hits = [p for p in paths if any(_glob_match(p, pat) for pat in patterns)]
                if hits:
                    out.setdefault((name, split), []).extend(hits)
        if out:
            return out
    for p in paths:
        out.setdefault(("default", infer_split(p)), []).append(p)
    return out


def _data_file_patterns(data_files: Any) -> list[tuple[str, list[str]]]:
    if data_files is None:
        return []
    if isinstance(data_files, str):
        return [("train", [data_files])]
    if isinstance(data_files, dict):
        return [(str(k), v if isinstance(v, list) else [str(v)]) for k, v in data_files.items()]
    out = []
    if isinstance(data_files, list):
        loose = []
        for item in data_files:
            if isinstance(item, dict) and "path" in item:
                pat = item["path"]
                out.append((str(item.get("split", "train")),
                            [str(x) for x in pat] if isinstance(pat, list) else [str(pat)]))
            elif isinstance(item, str):
                loose.append(item)
        if loose:
            out.append(("train", loose))
    return out


def missing_data_files(configs: Any, paths: list[str]) -> list[tuple[str, str]]:
    """(config, pattern) for every configs[].data_files pattern that matches no repo file."""
    out: list[tuple[str, str]] = []
    if not isinstance(configs, list):
        return out
    for cfg in configs:
        if not isinstance(cfg, dict):
            continue
        name = str(cfg.get("config_name", "default"))
        for _split, patterns in _data_file_patterns(cfg.get("data_files")):
            for pat in patterns:
                if "://" in pat:
                    continue
                if not any(_glob_match(p, pat) for p in paths):
                    out.append((name, pat))
    return out


def infer_split(path: str) -> str:
    tokens = re.split(r"[/_.\-\s]+", path.lower())
    for split, words in SPLIT_WORDS.items():
        if any(t in words for t in tokens):
            return split
    return "train"


_META_SKIP = {"configs", "dataset_info", "train-eval-index"}
_STATED_META = ("homepage", "repository", "repo", "url", "source", "paper", "website", "code")


def _walk_strings(obj: Any, prefix: str) -> list[tuple[str, str]]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if prefix == "" and k in _META_SKIP:
                continue
            out += _walk_strings(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for v in obj:
            out += _walk_strings(v, prefix)
    elif isinstance(obj, str):
        out.append((prefix, obj))
    return out


def _clean_url(u: str) -> str:
    return u.rstrip(".,;:!?*_")


def _line_of(card: Card, needle: str) -> int | None:
    if not card.text:
        return None
    for n, line in enumerate(card.text.splitlines(), start=1):
        if needle in line:
            return n
    return None


def extract_links(card: Card) -> list[LinkRef]:
    """Stated sources and other link-check targets from a card, deduplicated by URL."""
    found: list[LinkRef] = []
    seen: set[str] = set()

    def add(url: str, label: str, stated: bool) -> None:
        url = _clean_url(url)
        if url in seen:
            if stated:
                for ref in found:
                    if ref.url == url:
                        ref.stated = True
            return
        seen.add(url)
        line = _line_of(card, url)
        ev = Evidence(url=_with_line(card.evidence.url, line), revision=card.evidence.revision,
                      path=card.evidence.path, lines=[line, line] if line else None)
        found.append(LinkRef(url=url, label=label, stated=stated, evidence=ev))

    meta = card.metadata
    for key, value in _walk_strings(meta, ""):
        top = key.split(".", 1)[0]
        for u in _URL_RE.findall(value):
            if top == "license_link":
                add(u, "license_link", False)
            elif top == "source_datasets":
                add(u, "source_datasets", True)
            else:
                add(u, f"metadata: {key}", top.lower() in _STATED_META)
    for line in card.body.splitlines():
        m = _BULLET_RE.match(line)
        if m:
            label = m.group(1).strip().rstrip(":").strip()
            if label.lower().startswith(STATED_LABELS):
                for u in _URL_RE.findall(m.group(2)):
                    add(u, label, True)
                continue
        # labelled Markdown links, e.g. "[Website](https://...) | [Paper](https://...)"
        for text, u in _MD_LINK_RE.findall(line):
            label = re.sub(r"^[^\w]+", "", text).strip()
            if label.lower().startswith(STATED_LABELS) and len(label) <= 30:
                add(u, label, True)
    return found


def _with_line(url: str | None, line: int | None) -> str | None:
    if not url or not line:
        return url
    return f"{url.split('#')[0]}#L{line}"
