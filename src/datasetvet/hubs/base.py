"""Hub adapter and source resolver interfaces, plus the registry (PLAN.md section 6). Task 2.3.

The method set below is the contract every hub (Hugging Face in v1; Kaggle, Zenodo,
GitHub-hosted in v2) implements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from datasetvet.model import DatasetRef, Evidence


@dataclass
class Card:
    """A dataset card: raw text, parsed metadata, and where the YAML keys sit."""

    text: str | None  # full README text; None when there is no card file
    metadata: dict[str, Any]
    body: str  # README text with the YAML front matter removed
    evidence: Evidence
    key_lines: dict[str, int] = field(default_factory=dict)  # top-level YAML key -> line no.
    body_offset: int = 0  # number of lines before the body starts
    yaml_error: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class RepoFile:
    path: str
    size: int | None = None


@dataclass
class TextBlob:
    path: str
    text: str
    truncated: bool
    evidence: Evidence


@dataclass
class LicenceClaim:
    """A raw licence statement. Normalisation to SPDX is Phase 3."""

    source: str  # "card field", "readme text", "licence file", "source"
    raw: str
    evidence: Evidence


@dataclass
class LinkRef:
    url: str
    label: str  # e.g. "Homepage", "license_link", "metadata: homepage"
    stated: bool  # a stated source (counts for the card's "stated source" rule)
    evidence: Evidence | None = None


@dataclass
class ParentRef:
    raw: str  # value as written in source_datasets
    hub: str | None = None
    id: str | None = None
    url: str | None = None


@dataclass
class SplitFile:
    url: str
    path: str
    size: int | None
    fmt: str  # "parquet", "csv", "tsv", "jsonl"


@dataclass
class SplitSource:
    config: str
    split: str
    files: list[SplitFile]
    rows: int | None
    bytes: int | None
    source: str  # "parquet conversion" or "original files"
    revision: str | None
    partial: bool = False
    label_columns: list[str] = field(default_factory=list)
    label_names: dict[str, list[str]] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.config}/{self.split}"


@dataclass
class DataPlan:
    """What the adapter could find about the data, before the scan planner decides."""

    splits: list[SplitSource]
    not_checked: str | None = None  # reason no data can be read, if any
    notes: list[str] = field(default_factory=list)


@runtime_checkable
class HubAdapter(Protocol):
    name: str

    def matches(self, ref: str) -> bool: ...
    def resolve(self, ref: str) -> DatasetRef: ...
    def card(self, ds: DatasetRef) -> Card: ...
    def files(self, ds: DatasetRef) -> list[RepoFile]: ...
    def read_text(self, ds: DatasetRef, path: str, max_bytes: int) -> TextBlob: ...
    def native_licences(self, ds: DatasetRef) -> list[LicenceClaim]: ...
    def stated_sources(self, card: Card) -> list[LinkRef]: ...
    def parents(self, card: Card) -> list[ParentRef]: ...
    def splits(self, ds: DatasetRef, card: Card | None = None) -> DataPlan: ...
    def fetch(self, f: SplitFile, dest_dir: Path) -> Path: ...  # one file, to a temp dir
    def blob_url(self, ds: DatasetRef, path: str, line: int | None = None) -> str: ...


class SourceResolver(Protocol):
    def matches(self, url: str) -> bool: ...
    def licence_claims(self, url: str) -> list[LicenceClaim]: ...


class UnknownRefError(ValueError):
    pass


class Registry:
    def __init__(self) -> None:
        self.adapters: list[HubAdapter] = []
        self.resolvers: list[SourceResolver] = []

    def add_adapter(self, adapter: HubAdapter) -> None:
        self.adapters.append(adapter)

    def add_resolver(self, resolver: SourceResolver) -> None:
        self.resolvers.append(resolver)

    def adapter_for(self, ref: str) -> HubAdapter:
        for a in self.adapters:
            if a.matches(ref):
                return a
        forms = "hf:org/name, hf:org/name@revision, https://huggingface.co/datasets/org/name"
        raise UnknownRefError(f"No hub adapter understands {ref!r}. Supported forms: {forms}")

    def resolver_for(self, url: str) -> SourceResolver | None:
        for r in self.resolvers:
            if r.matches(url):
                return r
        return None
