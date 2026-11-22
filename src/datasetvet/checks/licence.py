"""Licence consistency, C1 vs C2/C3/C4 (PLAN.md 5.2). Task 3.6.

Never sampled. Statuses: consistent / inconsistent / missing / unknown, one per comparison.

- C1 card field: the card's YAML `license`, through HF's id table (`licences/hf_ids.py`).
- C2 card text: the README body (YAML stripped), read by the scanner.
- C3 repo licence files: LICEN[CS]E*, COPYING*, *.license anywhere in the repo.
- C4 sources: each stated GitHub repo, licence/terms page, licence URL, HF dataset, and the
  card's `license_link`. `source_datasets` parents are the provenance check's job.

C1 is compared with each other claim on its own; C2-C4 are never compared with each other.
Every sentence shows both sides verbatim with where each was read.

Phase 5.5 rules (PLAN.md 5.2, "Phase 5.5"):
- A stated source's GitHub repo licence file (not a DATA_LICENSE file) that names only
  OSI-approved software licences, while the card names a licence that is not one, is the source
  code licence: that comparison is `unknown` with the fact "the source code licence differs",
  not `inconsistent`.
- A text naming several licences is `consistent` when, after setting aside OSI-approved
  software licences the card does not name, the rest is exactly the card's set (again only when
  the card names a licence that is not OSI-approved).
- `licence.summary` gives one status for the dataset; a card licence that nothing read states
  or contradicts is `consistent` with the sub-fact "uncontradicted", never "confirmed".
The OSI-approved flag (SPDX licence list) is the only licence property that decides anything.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from datasetvet.hubs.base import Card, HubAdapter, LicenceClaim, LinkRef, SourceRead, TextBlob
from datasetvet.licences import spdx
from datasetvet.licences.hf_ids import HfLicence, lookup
from datasetvet.licences.matcher import Detection, licence_for_url
from datasetvet.licences.properties import properties
from datasetvet.licences.scanner import Scanner
from datasetvet.model import CheckResult, DatasetRef, Evidence, Fact, Family, LicenceStatus

LICENCE_FILE_RE = re.compile(r"(^|/)(licen[cs]e[^/]*|copying[^/]*|[^/]+\.license)$", re.IGNORECASE)
MAX_LICENCE_FILES = 10
MAX_LICENCE_BYTES = 512 * 1024
MAX_SOURCES = 10
PLACEHOLDER_RE = re.compile(r"\[?more information needed\]?", re.IGNORECASE)
_LICENSE_WORD_RE = re.compile(r"\blicen[cs](?:e|es|ed|ing)\b", re.IGNORECASE)
_DATA_FILE_RE = re.compile(r"data", re.IGNORECASE)  # DATA_LICENSE, LICENSE-DATA

# Phase 5.5 rules (module constants so the evaluation can measure each one; not user options).
CODE_LICENCE_RULE = True  # a source repo's software licence: "the source code licence differs"
SOFTWARE_ASIDE_RULE = True  # several licences in one text: set aside software licences
UNCONTRADICTED_RULE = True  # nothing read agrees or differs -> summary consistent (uncontradicted)
# the two code-licence rules apply only when the card names a licence that is not OSI-approved
# (a data or content licence such as CC-BY-4.0). Chosen on the rule-work rows (BUILD_LOG 5.5).
CODE_RULE_NEEDS_DATA_CARD = True


CODE_NOTE = ("Not counted as a contradiction: the repo's licence file names a software "
             "licence, and the card names a licence that is not one.")


def software_only(keys: set[str]) -> bool:
    """True when every key is OSI-approved on the SPDX licence list (a software licence)."""
    return bool(keys) and all(properties(k).osi for k in keys)


def card_names_data_licence(card_keys: set[str]) -> bool:
    return bool(card_keys) and (not CODE_RULE_NEEDS_DATA_CARD or not software_only(card_keys))


# -- the card's own claim (C1) ---------------------------------------------------------------

@dataclass
class CardLicence:
    """C1 for one card: what the YAML says and what it maps to."""

    values: list[str]
    lookups: list[HfLicence]
    evidence: Evidence
    where: str  # e.g. "README.md@3f2a1c9, YAML line 3"
    state: str  # "stated", "missing", "unclear"
    reason: str = ""  # why unclear
    expression: str | None = None
    license_name: str | None = None
    owner: str = "Card"  # "Card", "Parent org/name's card"

    def says(self) -> str:
        if self.state == "missing":
            shown = ", ".join(self.values) if self.values else "no `license`"
            return f"{self.owner} states no licence ({shown}; {self.where})"
        parts = []
        for h in self.lookups:
            if h.spdx and h.spdx != h.value:
                parts.append(f"{h.value} (SPDX {h.spdx})")
            elif h.kind == "non-spdx":
                parts.append(f"{h.value} ({h.name}, not on the SPDX list)")
            else:
                parts.append(h.value)
        text = " + ".join(parts)
        if self.license_name:
            text += f" with license_name {self.license_name!r}"
        return f"{self.owner} says {text} ({self.where})"

    def keys(self) -> set[str]:
        return spdx.keys(self.expression) if self.expression else set()


def card_licence(metadata: dict[str, Any], evidence: Evidence, where: str,
                 owner: str = "Card") -> CardLicence:
    raw = metadata.get("license")
    values = [str(v).strip() for v in (raw if isinstance(raw, list) else [raw])
              if v is not None and str(v).strip()]
    name = metadata.get("license_name")
    name = str(name) if name else None
    if not values or all(v.lower() == "unknown" for v in values):
        return CardLicence(values, [], evidence, where, "missing", owner=owner)
    looks = [lookup(v) for v in values if v.lower() != "unknown"]
    out = CardLicence(values, looks, evidence, where, "stated", license_name=name, owner=owner)
    for h in looks:
        if h.kind == "family":
            out.state, out.reason = "unclear", (f"{h.value} is a licence family on HF's list "
                                                "(not one licence)")
        elif h.kind == "special" and h.value.lower() == "other":
            out.state = "unclear"
            out.reason = ("license: other" + (f" with license_name {name!r}" if name else
                                              " without a license_name")
                          + ", which is not an id that can be compared")
        elif h.kind == "not-hf":
            out.state, out.reason = "unclear", f"{h.value!r} is neither an HF nor an SPDX id"
    if out.state == "stated":
        keys = [h.expression_key for h in looks if h.expression_key]
        out.expression = " AND ".join(dict.fromkeys(keys)) if keys else None
        if out.expression is None or spdx.parse(out.expression) is None:
            out.state, out.reason = "unclear", "the value does not form an SPDX expression"
    return out


def card_where(card: Card, sha: str | None) -> tuple[str, Evidence]:
    line = card.key_lines.get("license")
    url = card.evidence.url
    if url and line:
        url = f"{url.split('#')[0]}#L{line}"
    ev = Evidence(url=url, revision=card.evidence.revision, path=card.evidence.path or
                  "README.md", lines=[line, line] if line else None,
                  fetched_at=card.evidence.fetched_at)
    where = f"{ev.path}@{(sha or '?')[:7]}" + (f", YAML line {line}" if line else ", YAML")
    return where, ev


# -- the other side (C2, C3, C4, a parent's card) ---------------------------------------------

@dataclass
class OtherSide:
    label: str  # e.g. "README.md text", "LICENSE", "github.com/o/r LICENSE"
    where: str  # e.g. "LICENSE@9b1e0d4"
    evidence: Evidence | None
    state: str  # "read", "no statement", "unreadable", "unclear"
    detections: list[Detection] = field(default_factory=list)
    mentions_licence: bool = False  # licence words or a licence section, nothing identified
    note: str = ""
    card: CardLicence | None = None  # when the other side is another dataset's card field
    line_offset: int = 0  # added to detection lines (README body -> README lines)
    code_file: bool = False  # a source repo's general licence file (GitHub), not a data one
    no_file: bool = False  # a source repo where no licence file was found (not confirmed)


def _lines(d: Detection, offset: int) -> tuple[int, int] | None:
    if not d.lines:
        return None
    return d.lines[0] + offset, d.lines[1] + offset


def _describe(d: Detection, offset: int) -> str:
    how = d.method
    if d.score is not None:
        how += f", score {d.score:.0f}"
    ln = _lines(d, offset)
    if ln:
        how += f", line {ln[0]}" if ln[0] == ln[1] else f", lines {ln[0]}-{ln[1]}"
    return how


def _evidence_at(ev: Evidence | None, d: Detection, offset: int) -> Evidence | None:
    if ev is None:
        return None
    ln = _lines(d, offset)
    url = ev.url
    if url and ln and "#" not in url and ("github.com" in url or "huggingface.co" in url):
        url = f"{url}#L{ln[0]}" + (f"-L{ln[1]}" if ln[1] != ln[0] else "")
    return Evidence(url=url, revision=ev.revision, path=ev.path, fetched_at=ev.fetched_at,
                    lines=list(ln) if ln else None, note=ev.note)


def side_from_text(blob: TextBlob, scanner: Scanner, label: str, where: str,
                   line_offset: int = 0, extra: list[Detection] | None = None) -> OtherSide:
    dets = scanner.detect(blob.text) + (extra or [])
    mentions = bool(_LICENSE_WORD_RE.search(blob.text))
    side = OtherSide(label, where, blob.evidence, "read", dets, mentions_licence=mentions,
                     line_offset=line_offset)
    if blob.truncated:
        side.note = f"only the first {len(blob.text.encode()):,} bytes were read"
    if not dets and not mentions:
        side.state = "no statement"
    return side


def detection_from_claim(c: LicenceClaim) -> Detection | None:
    sid = spdx.spdx_id(c.raw) or (spdx.normalise(c.raw) if c.raw != "NOASSERTION" else None)
    if not sid:
        return None
    return Detection(sid, c.source, None, None, c.raw)


# -- comparison -----------------------------------------------------------------------------

@dataclass
class Outcome:
    status: LicenceStatus
    sentence: str
    sub: str | None = None  # "differs" / "subset" / reason for unknown
    extra: list[str] = field(default_factory=list)


def _side_says(o: OtherSide, dets: list[Detection]) -> str:
    if o.card is not None:
        return o.card.says()
    shown = "; ".join(
        f"{d.expression}"
        + (f" (same text as {', '.join(d.alternatives)})" if d.alternatives else "")
        + f" ({_describe(d, o.line_offset)})" for d in dets)
    return f"{o.where} says {shown}"


def compare(card: CardLicence, o: OtherSide) -> Outcome:
    """PLAN.md 5.2's rule, one comparison."""
    if o.state == "unreadable":
        return Outcome(LicenceStatus.UNKNOWN, f"{card.says()}; {o.where} could not be read: "
                       f"{o.note}.", "unreadable")
    if o.card is not None:  # another dataset's card field
        other = o.card
        if card.state == "missing" or other.state == "missing":
            who = [c.owner for c in (card, other) if c.state == "missing"]
            return Outcome(LicenceStatus.MISSING, f"{card.says()}; {other.says()}.",
                           f"no licence stated by: {', '.join(who)}")
        if card.state == "unclear" or other.state == "unclear":
            why = card.reason if card.state == "unclear" else other.reason
            return Outcome(LicenceStatus.UNKNOWN, f"{card.says()}; {other.says()}; "
                           f"not compared: {why}.", "unclear")
        assert other.expression is not None
        dets = [Detection(other.expression, "card field", None)]
    else:
        dets = [d for d in o.detections]
    if card.state == "missing":
        if not dets:
            return Outcome(LicenceStatus.MISSING, f"{card.says()}; {o.where} has no licence "
                           "statement either.", "both missing")
        return Outcome(LicenceStatus.MISSING, f"{card.says()}; {_side_says(o, dets)}.",
                       "card missing")
    if not dets:
        if o.state == "no statement" or (o.mentions_licence is False):
            return Outcome(LicenceStatus.MISSING, f"{card.says()}; {o.where} has no licence "
                           "statement.", "no statement")
        what = o.note or "it mentions a licence, but no licence was identified in it"
        return Outcome(LicenceStatus.UNKNOWN, f"{card.says()}; {o.where}: {what}.",
                       "no licence file found" if o.no_file else "not identified")
    if card.state == "unclear":
        return Outcome(LicenceStatus.UNKNOWN, f"{card.says()}; {_side_says(o, dets)}; "
                       f"not compared: {card.reason}.", "card unclear")
    assert card.expression is not None
    if all(d.versionless for d in dets):
        return Outcome(LicenceStatus.UNKNOWN, f"{card.says()}; {_side_says(o, dets)}; not "
                       "compared: the text names a Creative Commons licence without a version.",
                       "versionless")
    dets = [d for d in dets if not d.versionless]
    exprs = list(dict.fromkeys(d.expression for d in dets))
    refs = [e for e in exprs + [card.expression] if "LicenseRef-" in e]
    if len(exprs) > 1:
        all_keys = set().union(*(spdx.keys(e) for e in exprs))
        if all_keys == card.keys():
            return Outcome(LicenceStatus.CONSISTENT, f"{card.says()}; {_side_says(o, dets)}; "
                           "together these are the card's licences.", "same set")
        if CODE_LICENCE_RULE and o.code_file and software_only(all_keys) and \
                card_names_data_licence(card.keys()):
            return Outcome(LicenceStatus.UNKNOWN, f"{card.says()}; {_side_says(o, dets)}; the "
                           "source code licence differs: these are OSI-approved software "
                           f"licences of the repo {o.label.split(' ')[0]}, and its licence "
                           "file does not say whether they cover the data.", "code licence",
                           [CODE_NOTE])
        if SOFTWARE_ASIDE_RULE and card_names_data_licence(card.keys()):
            aside = {k for k in all_keys - card.keys() if properties(k).osi}
            if aside and all_keys - aside == card.keys():
                return Outcome(
                    LicenceStatus.CONSISTENT, f"{card.says()}; {_side_says(o, dets)}; apart "
                    f"from {', '.join(sorted(aside))} (OSI-approved software licence"
                    f"{'s' if len(aside) > 1 else ''}, set aside as a code licence), these are "
                    "the card's licences.", "same set, plus software licences",
                    [(f"Set aside, not compared: {', '.join(sorted(aside))}, an OSI-approved "
                      "software licence the card does not name; the text may use it for "
                      "code.")])
        extra = []
        if not (all_keys & card.keys()):
            extra.append("None of these is the card's licence.")
        return Outcome(LicenceStatus.UNKNOWN, f"{card.says()}; {_side_says(o, dets)}; not "
                       f"compared: {o.where} states {len(exprs)} different licences, and which "
                       "applies to what is not determined.", "several licences", extra)
    d = dets[0]
    candidates = [d.expression] + d.alternatives
    if refs:
        same = any(e == card.expression for e in candidates)
        if same:
            return Outcome(LicenceStatus.CONSISTENT, f"{card.says()}; {_side_says(o, dets)}; "
                           "these name the same licence.", "same name")
        return Outcome(LicenceStatus.UNKNOWN, f"{card.says()}; {_side_says(o, dets)}; not "
                       "compared: a licence that is not on the SPDX list can only be compared "
                       "by its exact name.", "non-SPDX")
    rels = [(e, spdx.relation(card.expression, e)) for e in candidates]
    for e, r in rels:
        if r.kind == "equivalent":
            extra = []
            if d.alternatives:
                extra.append(f"The text of {' and '.join(candidates)} is the same, so this "
                             "text alone does not say which of them it is.")
            return Outcome(LicenceStatus.CONSISTENT, f"{card.says()}; {_side_says(o, dets)}; "
                           "these are the same licence.", "equivalent", extra)
    _e, r = rels[0]
    if r.kind == "unparsed":
        return Outcome(LicenceStatus.UNKNOWN, f"{card.says()}; {_side_says(o, dets)}; not "
                       f"compared: {r.detail!r} is not an SPDX expression.", "unparsed")
    if CODE_LICENCE_RULE and o.code_file and software_only(spdx.keys(d.expression)) and \
            card_names_data_licence(card.keys()):
        return Outcome(LicenceStatus.UNKNOWN, f"{card.says()}; {_side_says(o, dets)}; the "
                       f"source code licence differs: {d.expression} is an OSI-approved "
                       f"software licence of the repo {o.label.split(' ')[0]}, and its "
                       "licence file does not say whether it covers the data.", "code licence",
                       [CODE_NOTE])
    if r.kind == "subset":
        return Outcome(LicenceStatus.INCONSISTENT, f"{card.says()}; {_side_says(o, dets)}; "
                       f"one is part of the other ({r.detail}).", "subset")
    return Outcome(LicenceStatus.INCONSISTENT, f"{card.says()}; {_side_says(o, dets)}; these "
                   "differ.", "differs")


def outcome_result(check: str, title: str, family: Family, card: CardLicence, o: OtherSide,
                   out: Outcome) -> CheckResult:
    evs = [card.evidence]
    if o.card is not None:
        evs.append(o.card.evidence)
    else:
        for d in o.detections[:3]:
            ev = _evidence_at(o.evidence, d, o.line_offset)
            if ev:
                evs.append(ev)
        if not o.detections and o.evidence:
            evs.append(o.evidence)
    facts = [Fact(out.sentence, evs, {"sub": out.sub})]
    facts += [Fact(x) for x in out.extra]
    if o.note and o.note not in out.sentence:
        facts.append(Fact(f"Note: {o.note}."))
    seen = set(card.keys())
    other_keys: set[str] = set()
    if o.card is not None:
        other_keys = o.card.keys()
    else:
        for d in o.detections:
            if not d.versionless:
                other_keys |= spdx.keys(d.expression)
    for k in sorted(other_keys - seen):
        facts.append(Fact("Properties: " + properties(k).text() + "."))
    data = {"sub": out.sub, "card": card.expression, "card_values": card.values,
            "other": [d.as_dict() for d in o.detections] if o.card is None else
            {"values": o.card.values, "expression": o.card.expression}}
    return CheckResult(check, family, out.status, title, facts, data)


# -- collecting the claims -------------------------------------------------------------------

@dataclass
class LicenceContext:
    adapter: HubAdapter
    ds: DatasetRef
    card: Card
    scanner: Scanner
    resolvers: list[Any]  # SourceResolver: github, web (in that order)
    hf_card_licence: Callable[[str], tuple[CardLicence | None, str]]  # id -> (C1, note)
    say: Callable[[str], None] = lambda _m: None


def readme_side(ctx: LicenceContext) -> OtherSide:
    card = ctx.card
    sha7 = ctx.ds.revision[:7]
    where = f"README.md@{sha7} (text below the YAML)"
    if card.text is None:
        return OtherSide("README text", where, card.evidence, "unreadable",
                         note=card.evidence.note or "no README text")
    body = card.body or ""
    blob = TextBlob("README.md", body, False, Evidence(
        url=ctx.adapter.blob_url(ctx.ds, "README.md"), revision=ctx.ds.revision,
        path="README.md", fetched_at=card.evidence.fetched_at))
    side = side_from_text(blob, ctx.scanner, "README text", where,
                          line_offset=card.body_offset)
    if not side.detections and side.mentions_licence and _only_placeholder(body):
        side.state = "no statement"
        side.mentions_licence = False
        side.note = "the licence section says only [More Information Needed]"
    return side


def _only_placeholder(body: str) -> bool:
    """True when every licence section in the body holds only HF's template placeholder and
    the word licen[cs]e appears nowhere else outside headings."""
    from datasetvet.licences.matcher import _licence_lines

    raw = body.splitlines()
    lines = [_MD_LINK_RE.sub(lambda m: m.group(1), ln) for ln in raw]
    ctx = _licence_lines(lines)
    rest = [ln for n, (ln, orig) in enumerate(zip(lines, raw, strict=True), 1)
            if n not in ctx and not _TOC_RE.match(orig)]
    if any(_LICENSE_WORD_RE.search(ln) for ln in rest):
        return False
    content = [ln.strip() for n, ln in enumerate(lines, 1) if n in ctx
               and not ln.lstrip().startswith("#") and ln.strip()]
    return bool(content) and all(PLACEHOLDER_RE.fullmatch(c.strip("*_ ")) for c in content)


_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TOC_RE = re.compile(r"^\s*[-*+]\s*\[[^\]]*\]\(#[^)]*\)\s*$")
# HF's old card template links "[More Information Needed]" to this file; it is not a source
TEMPLATE_LINK_RE = re.compile(r"github\.com/huggingface/datasets/blob/[^/]+/CONTRIBUTING\.md",
                              re.IGNORECASE)


def licence_files(ctx: LicenceContext) -> tuple[list[OtherSide], list[str]]:
    listing = ctx.adapter.listing(ctx.ds)
    paths = [f.path for f in listing.files if LICENCE_FILE_RE.search(f.path)]
    sides = []
    for path in sorted(paths)[:MAX_LICENCE_FILES]:
        where = f"{path}@{ctx.ds.revision[:7]}"
        try:
            blob = ctx.adapter.read_text(ctx.ds, path, MAX_LICENCE_BYTES)
        except Exception as exc:  # noqa: BLE001  gated (401) or fetch failure
            sides.append(OtherSide(path, where, Evidence(
                url=ctx.adapter.blob_url(ctx.ds, path), revision=ctx.ds.revision, path=path),
                "unreadable", note=str(exc)[:120] or type(exc).__name__))
            continue
        sides.append(side_from_text(blob, ctx.scanner, path, where))
    nc = []
    if not listing.complete:
        nc.append(f"licence files: a licence file outside the repo's partial file list would "
                  f"be missed ({listing.note})")
    if len(paths) > MAX_LICENCE_FILES:
        nc.append(f"licence files beyond the first {MAX_LICENCE_FILES} "
                  f"({len(paths) - MAX_LICENCE_FILES} more)")
    return sides, nc


_HF_DS_RE = re.compile(r"^https?://(?:www\.)?huggingface\.co/datasets/([^/\s?#]+/[^/\s?#]+)",
                       re.IGNORECASE)


def source_targets(links: list[LinkRef], ds: DatasetRef) -> list[LinkRef]:
    """Stated sources and license_link, minus source_datasets (provenance), the dataset's own
    repo, and duplicates of the same GitHub repo or HF dataset."""
    from datasetvet.hubs.github import parse_repo

    out: list[LinkRef] = []
    seen: set[str] = set()
    for ln in links:
        if not (ln.stated or ln.label == "license_link") or ln.label == "source_datasets":
            continue
        if TEMPLATE_LINK_RE.search(ln.url):
            continue
        m = _HF_DS_RE.match(ln.url)
        if m and m.group(1).lower() == ds.id.lower():
            continue
        gh = parse_repo(ln.url)
        key = (f"gh:{gh[0].lower()}/{gh[1].lower()}" if gh else
               f"hf:{m.group(1).lower()}" if m else ln.url)
        if key in seen:
            continue
        seen.add(key)
        out.append(ln)
    return out


def source_sides(ctx: LicenceContext, links: list[LinkRef]) -> tuple[list[tuple[LinkRef,
                                                                                 OtherSide]],
                                                                       list[str]]:
    pairs: list[tuple[LinkRef, OtherSide]] = []
    skipped: list[str] = []
    targets = source_targets(links, ctx.ds)
    for ln in targets[:MAX_SOURCES]:
        m = _HF_DS_RE.match(ln.url)
        if m:
            ctx.say(f"reading the card of {m.group(1)}")
            c1, note = ctx.hf_card_licence(m.group(1))
            if c1 is None:
                pairs.append((ln, OtherSide(f"HF dataset {m.group(1)}", f"{m.group(1)}'s card",
                                            None, "unreadable", note=note)))
            else:
                pairs.append((ln, OtherSide(f"HF dataset {m.group(1)}", c1.where, c1.evidence,
                                            "read", card=c1)))
            continue
        resolver = next((r for r in ctx.resolvers if r.matches(ln.url)), None)
        if resolver is None:
            skipped.append(f"{ln.url} (no resolver)")
            continue
        ctx.say(f"reading the licence of {ln.url}")
        read: SourceRead = resolver.read(ln.url)
        if read.state == "skipped":
            skipped.append(f"{read.label} ({read.note})")
            continue
        pairs += [(ln, s) for s in sides_from_read(read, ctx.scanner)]
    if len(targets) > MAX_SOURCES:
        skipped.append(f"{len(targets) - MAX_SOURCES} more stated sources (limit "
                       f"{MAX_SOURCES})")
    return pairs, skipped


def sides_from_read(read: SourceRead, scanner: Scanner) -> list[OtherSide]:
    rev = f"@{read.revision[:7]}" if read.revision else ""
    if read.state == "unreadable":
        return [OtherSide(read.label, read.label, Evidence(url=read.url), "unreadable",
                          note=read.note or "")]
    if read.state == "no licence file":
        side = OtherSide(read.label, f"{read.label}{rev}", Evidence(url=read.url,
                         revision=read.revision), "no statement" if read.confirmed_none
                         else "read", note=read.note or "")
        side.mentions_licence = not read.confirmed_none  # unknown unless GitHub confirms none
        side.no_file = not read.confirmed_none
        return [side]
    claim_dets = [d for d in (detection_from_claim(c) for c in read.claims) if d]
    noassert = [c for c in read.claims if c.raw == "NOASSERTION"]
    if not read.texts:  # a licence URL, or only GitHub's detection
        ev = read.claims[0].evidence if read.claims else Evidence(url=read.url)
        side = OtherSide(read.label, read.label, ev, "read", claim_dets,
                         mentions_licence=True, code_file=read.kind == "github")
        return [side]
    sides = []
    for i, blob in enumerate(read.texts):
        where = f"{read.label} {blob.path}{rev}"
        side = side_from_text(blob, scanner, f"{read.label} {blob.path}", where)
        side.code_file = read.kind == "github" and not _DATA_FILE_RE.search(
            blob.path.rsplit("/", 1)[-1])
        if i == 0 and (claim_dets or noassert):
            own = {spdx.normalise(d.expression) for d in side.detections}
            gh = {spdx.normalise(d.expression) for d in claim_dets}
            if noassert:
                side.note = "GitHub's detection (licensee): NOASSERTION (a licence file it " \
                            "could not identify)"
            elif own and gh and own != gh:
                side.detections = side.detections + claim_dets  # several -> unknown
                side.note = (f"our scanner and GitHub's detection disagree ("
                             f"{', '.join(sorted(x or '?' for x in own))} vs "
                             f"{', '.join(sorted(x or '?' for x in gh))})")
            elif not own:
                side.detections = claim_dets
                side.note = "identified by GitHub's detection (licensee), not by our scanner"
            else:
                side.note = "GitHub's detection (licensee) agrees"
        sides.append(side)
    return sides


# -- one status for the dataset (Phase 5.5) ---------------------------------------------------

# unknown comparisons that are not evidence either way: a source repo's software licence, a
# source repo where no licence file was found anonymously, a stated source that could not be read
_NOT_EVIDENCE = {"code licence", "no licence file found"}


def _blocks(r: CheckResult) -> bool:
    sub = r.data.get("sub")
    if sub in _NOT_EVIDENCE:
        return False
    return not (r.check.startswith("licence.source:") and sub == "unreadable")


def summarise(c1: CardLicence, results: list[CheckResult]) -> CheckResult:
    """One status for the dataset, from the card (C1) and every comparison:
    card states no licence -> missing; card value not comparable -> unknown; any comparison
    inconsistent -> inconsistent; any consistent -> consistent ("confirmed"); any other unknown
    that is evidence (a text naming a licence we could not compare, the dataset's own README or
    licence file unreadable) -> unknown; otherwise consistent ("uncontradicted": nothing read
    states a licence that agrees or differs)."""
    fam = Family.LICENCE
    title = "Licence, overall"

    def done(status: LicenceStatus, sub: str, sentence: str, more: list[str] | None = None
             ) -> CheckResult:
        facts = [Fact(sentence, [c1.evidence], {"sub": sub})] + [Fact(x) for x in more or []]
        return CheckResult("licence.summary", fam, status, title, facts,
                           {"sub": sub, "card": c1.expression, "card_values": c1.values,
                            "comparisons": len(results)})

    def names(rs: list[CheckResult]) -> str:
        return "; ".join(r.title.removeprefix("Card vs ") for r in rs)

    if c1.state == "missing":
        return done(LicenceStatus.MISSING, "card missing", f"{c1.says()}.")
    if c1.state == "unclear":
        return done(LicenceStatus.UNKNOWN, "card unclear",
                    f"{c1.says()}; not compared: {c1.reason}.")
    by = {s: [r for r in results if r.status == s] for s in LicenceStatus}
    aside = [r for r in by[LicenceStatus.UNKNOWN] if r.data.get("sub") == "code licence"]
    more = ([(f"Not counted as a contradiction (the source code licence differs): "
              f"{names(aside)}.")] if aside else [])
    if by[LicenceStatus.INCONSISTENT]:
        rs = by[LicenceStatus.INCONSISTENT]
        return done(LicenceStatus.INCONSISTENT, "differs",
                    f"{c1.says()}; {len(rs)} of {len(results)} comparisons differ from it: "
                    f"{names(rs)}.", more)
    if by[LicenceStatus.CONSISTENT]:
        rs = by[LicenceStatus.CONSISTENT]
        return done(LicenceStatus.CONSISTENT, "confirmed",
                    f"{c1.says()}; confirmed by {names(rs)}, and no comparison differs.", more)
    open_ = [r for r in by[LicenceStatus.UNKNOWN] if _blocks(r)]
    if open_ or not UNCONTRADICTED_RULE:
        return done(LicenceStatus.UNKNOWN, "unresolved",
                    f"{c1.says()}; no comparison agrees or differs, and these could not be "
                    f"compared: {names(open_)}.", more)
    return done(LicenceStatus.CONSISTENT, "uncontradicted",
                f"{c1.says()}; uncontradicted, not confirmed: none of the {len(results)} "
                "places compared states a licence that agrees or differs.", more)


def check_licence(ctx: LicenceContext, links: list[LinkRef]) -> tuple[list[CheckResult],
                                                                       list[str]]:
    """All C1-vs-C2/C3/C4 comparisons. Returns (results, not-checked notes)."""
    where, ev = card_where(ctx.card, ctx.ds.revision)
    c1 = card_licence(ctx.card.metadata, ev, where)
    results: list[CheckResult] = []
    not_checked: list[str] = []
    fam = Family.LICENCE

    side = readme_side(ctx)
    results.append(outcome_result("licence.readme", "Card vs README text", fam, c1, side,
                                  compare(c1, side)))

    files, nc = licence_files(ctx)
    not_checked += nc
    if not files:
        not_checked.append("licence files: the repo has none (no LICEN[CS]E*, COPYING* or "
                           "*.license), so there is nothing to compare")
    for f in files:
        results.append(outcome_result(f"licence.file:{f.label}", f"Card vs {f.label}", fam,
                                      c1, f, compare(c1, f)))

    pairs, skipped = source_sides(ctx, links)
    for ln, s in pairs:
        title = ("Card vs license_link " if ln.label == "license_link" else "Card vs source ") \
            + s.label
        results.append(outcome_result(f"licence.source:{s.label}", title, fam, c1, s,
                                      compare(c1, s)))
    if skipped:
        not_checked.append("stated sources not read for a licence (not a GitHub repo, HF "
                           "dataset or licence page): " + "; ".join(skipped))
    if not pairs:
        not_checked.append("source licence: no stated source that is a GitHub repo, HF "
                           "dataset, licence URL or licence page")
    return [summarise(c1, results)] + results, not_checked


def is_licence_url(url: str) -> bool:
    return licence_for_url(url) is not None
