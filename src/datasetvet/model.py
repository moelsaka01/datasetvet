"""Dataclasses and status enums (PLAN.md section 5). Task 2.1.

The JSON report is the single source of truth; every other format renders from `Report.to_dict()`.
Statuses are closed sets: a check family can only emit the values its enum allows.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "0.1"

FOOTER = (
    "Facts only, not legal advice. Statuses: consistent / inconsistent / missing / unknown. "
    "No check decides whether you may use this data."
)


class LicenceStatus(StrEnum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    MISSING = "missing"
    UNKNOWN = "unknown"


class CardStatus(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    INVALID = "invalid"


class LinkStatus(StrEnum):
    OK = "ok"
    DEAD = "dead"
    RESTRICTED = "restricted"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


class HealthStatus(StrEnum):
    NONE_FOUND = "none found"
    FOUND = "found"
    NOT_CHECKED = "not checked"


class Family(StrEnum):
    CARD = "card"
    LINKS = "links"
    HEALTH = "health"
    LICENCE = "licence"
    PROVENANCE = "provenance"


STATUS_ENUM: dict[Family, type[StrEnum]] = {
    Family.CARD: CardStatus,
    Family.LINKS: LinkStatus,
    Family.HEALTH: HealthStatus,
    Family.LICENCE: LicenceStatus,
    Family.PROVENANCE: LicenceStatus,
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class Evidence:
    """Where a fact comes from. `revision` is a commit sha whenever the hub has one."""

    url: str | None = None
    revision: str | None = None
    path: str | None = None
    lines: list[int] | None = None  # [first, last], 1-based, inclusive
    fetched_at: str | None = None
    note: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Evidence:
        return cls(**d)


@dataclass
class Fact:
    """One verifiable sentence plus the evidence for it. `data` holds machine-readable values."""

    text: str
    evidence: list[Evidence] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Fact:
        return cls(
            text=d["text"],
            evidence=[Evidence.from_dict(e) for e in d.get("evidence", [])],
            data=d.get("data", {}),
        )


@dataclass
class CheckResult:
    check: str  # e.g. "card.citation", "links", "health.duplicates"
    family: Family
    status: str
    title: str = ""
    facts: list[Fact] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.family = Family(self.family)
        allowed = STATUS_ENUM[self.family]
        # Raises ValueError for a status the family does not allow.
        self.status = str(allowed(str(self.status)))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CheckResult:
        return cls(
            check=d["check"],
            family=Family(d["family"]),
            status=d["status"],
            title=d.get("title", ""),
            facts=[Fact.from_dict(f) for f in d.get("facts", [])],
            data=d.get("data", {}),
        )


@dataclass
class DatasetRef:
    hub: str
    id: str
    revision: str  # pinned commit sha
    requested: str  # what the user typed
    requested_revision: str | None = None
    url: str | None = None
    gated: bool | str = False
    private: bool = False
    disabled: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DatasetRef:
        return cls(**d)


@dataclass
class ScanInfo:
    """What the data-health pass covered. `kind` is "full", "sampled" or "not checked"."""

    kind: str = "not checked"
    rows_scanned: int = 0
    rows_total: int | None = None
    bytes_total: int | None = None
    bytes_read: int = 0
    seed: int | None = None
    source: str | None = None  # "parquet conversion" / "original files"
    source_revision: str | None = None
    reason: str | None = None  # why not checked, or why sampled
    seconds: float | None = None
    partial: bool = False

    def header(self) -> str:
        if self.kind == "full":
            return "Full scan" + (" (partial: some files failed)" if self.partial else "")
        if self.kind == "sampled":
            total = f"{self.rows_total:,}" if self.rows_total is not None else "unknown"
            text = f"Sampled: {self.rows_scanned:,} of {total} rows (seed {self.seed})"
            return text + (" (partial: some files failed)" if self.partial else "")
        return "Data not checked" + (f": {self.reason}" if self.reason else "")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScanInfo:
        return cls(**d)


@dataclass
class Report:
    dataset: DatasetRef
    tool_version: str
    scan: ScanInfo = field(default_factory=ScanInfo)
    results: list[CheckResult] = field(default_factory=list)
    not_checked: list[str] = field(default_factory=list)
    authenticated: bool = False
    created_at: str = field(default_factory=now_iso)
    scanner: str = "none (licence-text scanner not installed)"
    settings: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    footer: str = FOOTER

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Report:
        return cls(
            dataset=DatasetRef.from_dict(d["dataset"]),
            tool_version=d["tool_version"],
            scan=ScanInfo.from_dict(d.get("scan", {})),
            results=[CheckResult.from_dict(r) for r in d.get("results", [])],
            not_checked=list(d.get("not_checked", [])),
            authenticated=bool(d.get("authenticated", False)),
            created_at=d["created_at"],
            scanner=d.get("scanner", ""),
            settings=d.get("settings", {}),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            footer=d.get("footer", FOOTER),
        )

    def by_family(self, family: Family) -> list[CheckResult]:
        return [r for r in self.results if r.family == family]
