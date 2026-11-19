"""Provenance: declared parents' licences (PLAN.md 5.3). Task 3.7.

- Parents are only *declared*: the card's YAML `source_datasets` (`extended|<id>`, an HF id,
  or a URL a resolver can read). README links to other datasets are "mentioned", never parents.
- Each parent's licence is compared with its child's card field using the 5.2 rule and the
  same four statuses: an HF parent by its own card field, a GitHub or web parent by its
  licence files / licence page through the scanner.
- Depth limit 2 by default; cycles stop at the first repeat of (hub, id); every HF parent is
  pinned to the commit the Hub returns.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from datasetvet.checks.licence import (
    CardLicence,
    OtherSide,
    compare,
    outcome_result,
    sides_from_read,
)
from datasetvet.hubs.base import ParentRef
from datasetvet.licences.scanner import Scanner
from datasetvet.model import CheckResult, Evidence, Fact, Family, LicenceStatus

_HF_DS_RE = re.compile(r"^https?://(?:www\.)?huggingface\.co/datasets/([^/\s?#]+(?:/[^/\s?#]+)?)",
                       re.IGNORECASE)


@dataclass
class HfParent:
    """What the provenance check needs from an HF dataset: its pinned id, C1, and parents."""

    id: str
    revision: str
    licence: CardLicence
    parents: list[ParentRef]


@dataclass
class ProvenanceContext:
    child_id: str
    child_licence: CardLicence
    parents: list[ParentRef]
    resolve_hf: Callable[[str], tuple[HfParent | None, str]]  # id -> (parent, error note)
    resolvers: list[Any]
    scanner: Scanner
    depth: int = 2
    say: Callable[[str], None] = lambda _m: None


def mentioned_datasets(body: str, own_id: str, parent_ids: set[str]) -> list[str]:
    seen: list[str] = []
    for m in _HF_DS_RE.finditer(body or ""):
        ds = m.group(1).rstrip(".,;:)")
        if "/" not in ds or ds.lower() == own_id.lower() or ds.lower() in parent_ids:
            continue
        if ds not in seen:
            seen.append(ds)
    return seen


def check_provenance(ctx: ProvenanceContext) -> tuple[list[CheckResult], list[str]]:
    results: list[CheckResult] = []
    not_checked: list[str] = []
    visited = {("huggingface", ctx.child_id.lower())}
    _walk(ctx, ctx.child_id, ctx.child_licence, ctx.parents, 1, visited, results, not_checked)
    return results, not_checked


def _title(ref: ParentRef, child: str, root: str, level: int) -> str:
    name = ref.id or ref.url or ref.raw
    return f"Parent {name}" + (f" (parent of {child})" if level > 1 and child != root else "")


def _walk(ctx: ProvenanceContext, child_id: str, child: CardLicence, parents: list[ParentRef],
          level: int, visited: set[tuple[str, str]], results: list[CheckResult],
          not_checked: list[str]) -> None:
    fam = Family.PROVENANCE
    for ref in parents:
        check = f"provenance.parent:{ref.id or ref.url or ref.raw}"
        title = _title(ref, child_id, ctx.child_id, level)
        hf_id = ref.id if ref.hub == "huggingface" else None
        if ref.url and not hf_id:
            m = _HF_DS_RE.match(ref.url)
            hf_id = m.group(1) if m else None
        if hf_id:
            key = ("huggingface", hf_id.lower())
            if key in visited:
                results.append(CheckResult(check, fam, LicenceStatus.UNKNOWN, title, [Fact(
                    f"source_datasets value {ref.raw!r} in {child_id}'s card leads back to "
                    f"{hf_id}, which is already in this chain (a cycle); not followed again.",
                    [child.evidence])], {"cycle": True}))
                continue
            visited.add(key)
            ctx.say(f"reading parent {hf_id}")
            parent, note = ctx.resolve_hf(hf_id)
            if parent is None:
                results.append(CheckResult(check, fam, LicenceStatus.UNKNOWN, title, [Fact(
                    f"{child.says()}; parent {ref.raw!r} could not be read: {note}.",
                    [child.evidence])], {"parent": ref.raw}))
                continue
            visited.add(("huggingface", parent.id.lower()))
            side = OtherSide(f"parent {parent.id}", parent.licence.where,
                             parent.licence.evidence, "read", card=parent.licence)
            res = outcome_result(check, title, fam, child, side, compare(child, side))
            res.data.update({"parent": parent.id, "parent_revision": parent.revision,
                             "level": level, "declared_as": ref.raw})
            if parent.id.lower() != hf_id.lower():
                res.facts.append(Fact(f"{ref.raw!r} resolves to {parent.id} on the Hub."))
            results.append(res)
            if level < ctx.depth and parent.parents:
                _walk(ctx, parent.id, parent.licence, parent.parents, level + 1, visited,
                      results, not_checked)
            elif parent.parents:
                not_checked.append(f"provenance beyond depth {ctx.depth}: {parent.id} declares "
                                   f"{len(parent.parents)} parent(s) of its own")
            continue
        if ref.url:
            resolver = next((r for r in ctx.resolvers if r.matches(ref.url)), None)
            read = resolver.read(ref.url) if resolver else None
            if read is None or read.state == "skipped":
                why = read.note if read else "no resolver for this URL"
                results.append(CheckResult(check, fam, LicenceStatus.UNKNOWN, title, [Fact(
                    f"{child.says()}; parent {ref.url} was not read for a licence: {why}.",
                    [child.evidence, Evidence(url=ref.url)])], {"parent": ref.url}))
                continue
            for side in sides_from_read(read, ctx.scanner):
                res = outcome_result(check, f"{title}: {side.label}", fam, child, side,
                                     compare(child, side))
                res.data.update({"parent": ref.url, "level": level, "declared_as": ref.raw})
                results.append(res)
            continue
        results.append(CheckResult(check, fam, LicenceStatus.UNKNOWN, title, [Fact(
            f"source_datasets value {ref.raw!r} in {child_id}'s card does not name a dataset "
            "or URL that can be resolved, so its licence is unknown.", [child.evidence])],
            {"parent": ref.raw, "level": level}))
