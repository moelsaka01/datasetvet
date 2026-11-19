"""Card check (PLAN.md 5.1). Task 2.5.

Never sampled. Statuses: present / missing / invalid.

Licence field (task 3.1): each value is looked up in HF's licence id table
(`data/hf_licence_ids.csv`). `present` if every value is an HF id or an SPDX id; `invalid` if
a value is neither (or not a string); `missing` if absent, empty or `unknown`. Each value's
SPDX mapping and published properties are listed as facts.
"""

from __future__ import annotations

import re
from typing import Any

from datasetvet.hubs.base import Card, LinkRef
from datasetvet.licences import spdx
from datasetvet.licences.hf_ids import HfLicence, lookup
from datasetvet.licences.hf_ids import source_url as hf_source_url
from datasetvet.licences.properties import properties
from datasetvet.model import CardStatus, CheckResult, Evidence, Fact, Family

# HF's size_categories values (huggingface.co/docs/hub/datasets-cards, Hub validation list)
SIZE_CATEGORIES = {
    "n<1K", "1K<n<10K", "10K<n<100K", "100K<n<1M", "1M<n<10M", "10M<n<100M", "100M<n<1B",
    "1B<n<10B", "10B<n<100B", "100B<n<1T", "n>1T", "unknown",
}

_HEADING_RE = re.compile(r"^#\s+\S", re.MULTILINE)
# any heading whose text contains the word "citation" (emoji and other prefixes allowed)
_CITATION_HEAD_RE = re.compile(r"^(#{1,6})[ \t]+[^\n]*?\bcitations?\b[^\n]*$",
                               re.IGNORECASE | re.MULTILINE)
_BIBTEX_RE = re.compile(r"@\w+\s*\{")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+")
_ARXIV_RE = re.compile(r"\barxiv[:\s./]*(?:abs/)?\d{4}\.\d{4,5}", re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def _ev(card: Card, key: str | None = None, line: int | None = None) -> list[Evidence]:
    ln = line if line is not None else (card.key_lines.get(key) if key else None)
    url = card.evidence.url
    if url and ln:
        url = f"{url.split('#')[0]}#L{ln}"
    return [Evidence(url=url, revision=card.evidence.revision, path=card.evidence.path,
                     lines=[ln, ln] if ln else None, fetched_at=card.evidence.fetched_at,
                     note=card.evidence.note)]


def _values(v: Any) -> list[Any]:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v == [] or v == {}


def _result(check: str, title: str, status: CardStatus, facts: list[Fact],
            **data: Any) -> CheckResult:
    return CheckResult(check, Family.CARD, status, title, facts, dict(data))


def check_licence_field(card: Card) -> CheckResult:
    m = card.metadata
    raw = m.get("license")
    ev = _ev(card, "license")
    title = "Licence field"
    if "license" not in m or _is_blank(raw):
        return _result("card.licence", title, CardStatus.MISSING,
                       [Fact("The card's YAML has no `license` value.", ev)], values=[])
    vals = _values(raw)
    if not all(isinstance(v, str) for v in vals):
        return _result("card.licence", title, CardStatus.INVALID,
                       [Fact(f"`license` is not a string or a list of strings: {raw!r}.", ev)],
                       values=[str(v) for v in vals])
    vals = [v.strip() for v in vals if v.strip()]
    if not vals or all(v.lower() == "unknown" for v in vals):
        return _result("card.licence", title, CardStatus.MISSING,
                       [Fact(f"`license` is {', '.join(vals) or 'empty'}.", ev)], values=vals)
    facts = [Fact(f"Card says license: {', '.join(vals)}.", ev, {"values": vals})]
    bad = []
    for v in vals:
        if v.lower() == "unknown":
            continue
        h = lookup(v)
        facts.append(Fact(_mapping_text(h), ev, {"value": v, "kind": h.kind, "spdx": h.spdx}))
        if h.spdx:
            facts.append(Fact("Properties: " + properties(h.spdx).text() + "."))
        if h.kind == "not-hf":
            bad.append(v)
    if any(v.lower() == "other" for v in vals):
        name, link = m.get("license_name"), m.get("license_link")
        detail = []
        detail.append(f"license_name: {name}" if name else "no license_name")
        detail.append(f"license_link: {link}" if link else "no license_link")
        facts.append(Fact(f"`license: other` with {'; '.join(detail)}.",
                          _ev(card, "license_name" if name else "license"),
                          {"license_name": name, "license_link": link}))
    status = CardStatus.INVALID if bad else CardStatus.PRESENT
    return _result("card.licence", title, status, facts, values=vals, invalid=bad,
                   hf_list=hf_source_url())


def _mapping_text(h: HfLicence) -> str:
    if h.kind == "spdx":
        dep = " (a deprecated SPDX id)" if (spdx.flags(h.spdx or "") or (0, 0, 0))[2] else ""
        return f"{h.value}: HF licence id for SPDX {h.spdx}{dep}."
    if h.kind == "spdx-not-hf":
        return f"{h.value}: not on HF's licence id list, but the SPDX id {h.spdx}."
    if h.kind == "family":
        return f"{h.value}: HF id for a licence family ({h.name}), not one licence."
    if h.kind == "non-spdx":
        return f"{h.value}: HF id for {h.name}, which is not on the SPDX list."
    if h.kind == "special" and h.value.lower() == "other":
        return (f"{h.value}: HF's id for a licence not on its list; HF asks for the licence's "
                "name in license_name and its text in a LICENSE file.")
    if h.kind == "special":
        return f"{h.value}: HF's id for an unknown licence."
    return f"{h.value!r}: neither an HF licence id nor an SPDX id."


def _text_modality(card: Card) -> bool | None:
    mods = [t.split(":", 1)[1] for t in card.tags if t.startswith("modality:")]
    if not mods:
        return None
    return "text" in mods


def check_metadata(card: Card) -> list[CheckResult]:
    m = card.metadata
    out = []

    # pretty_name or a top-level heading
    if not _is_blank(m.get("pretty_name")):
        out.append(_result("card.pretty_name", "Dataset name", CardStatus.PRESENT,
                           [Fact(f"pretty_name: {m['pretty_name']}.", _ev(card, "pretty_name"))]))
    else:
        h = _HEADING_RE.search(card.body or "")
        if h:
            line = card.body_offset + card.body[:h.start()].count("\n") + 1
            heading = card.body[h.start():].splitlines()[0].lstrip("# ").strip()
            out.append(_result("card.pretty_name", "Dataset name", CardStatus.PRESENT,
                               [Fact(f"No pretty_name; top-level heading: {heading}.",
                                     _ev(card, line=line))]))
        else:
            out.append(_result("card.pretty_name", "Dataset name", CardStatus.MISSING,
                               [Fact("No pretty_name and no top-level (#) heading.",
                                     _ev(card))]))

    # language, required for text datasets (or when the modality is unknown)
    text_mod = _text_modality(card)
    if text_mod is not False:
        why = "text modality" if text_mod else "modality not stated, so treated as text"
        lang = m.get("language")
        if _is_blank(lang):
            out.append(_result("card.language", "Language", CardStatus.MISSING,
                               [Fact(f"No `language` ({why}).", _ev(card, "language"))]))
        elif not all(isinstance(v, str) for v in _values(lang)):
            out.append(_result("card.language", "Language", CardStatus.INVALID,
                               [Fact(f"`language` is not a string or list of strings: "
                                     f"{lang!r}.", _ev(card, "language"))]))
        else:
            out.append(_result("card.language", "Language", CardStatus.PRESENT,
                               [Fact(f"language: {', '.join(_values(lang))}.",
                                     _ev(card, "language"))]))

    tc = m.get("task_categories")
    if _is_blank(tc):
        out.append(_result("card.task_categories", "Task categories", CardStatus.MISSING,
                           [Fact("No `task_categories`.", _ev(card, "task_categories"))]))
    else:
        out.append(_result("card.task_categories", "Task categories", CardStatus.PRESENT,
                           [Fact(f"task_categories: {', '.join(map(str, _values(tc)))}.",
                                 _ev(card, "task_categories"))]))

    sc = m.get("size_categories")
    if _is_blank(sc):
        out.append(_result("card.size_categories", "Size category", CardStatus.MISSING,
                           [Fact("No `size_categories`.", _ev(card, "size_categories"))]))
    else:
        bad = [str(v) for v in _values(sc) if str(v) not in SIZE_CATEGORIES]
        status = CardStatus.INVALID if bad else CardStatus.PRESENT
        text = (f"size_categories value(s) not on HF's list: {', '.join(bad)}." if bad
                else f"size_categories: {', '.join(map(str, _values(sc)))}.")
        out.append(_result("card.size_categories", "Size category", status,
                           [Fact(text, _ev(card, "size_categories"))]))

    has_cfg = not _is_blank(m.get("configs"))
    has_info = not _is_blank(m.get("dataset_info"))
    if has_cfg or has_info:
        which = " and ".join(k for k, v in (("configs", has_cfg), ("dataset_info", has_info))
                             if v)
        out.append(_result("card.configs", "Configs / dataset_info", CardStatus.PRESENT,
                           [Fact(f"The card has {which}.",
                                 _ev(card, "configs" if has_cfg else "dataset_info"))]))
    else:
        out.append(_result("card.configs", "Configs / dataset_info", CardStatus.MISSING,
                           [Fact("Neither `configs` nor `dataset_info` in the YAML.",
                                 _ev(card))]))
    return out


def _section(body: str, head: re.Match[str]) -> str:
    level = len(head.group(1))
    rest = body[head.end():]
    nxt = re.search(rf"^#{{1,{level}}}\s", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def check_citation(card: Card) -> CheckResult:
    body = card.body or ""
    title = "Citation"

    def line_at(pos: int) -> int:
        return card.body_offset + body[:pos].count("\n") + 1

    for head in _CITATION_HEAD_RE.finditer(body):
        sec = _section(body, head)
        for block in _CODE_BLOCK_RE.findall(sec):
            if block.strip():
                return _result("card.citation", title, CardStatus.PRESENT, [Fact(
                    "A citation section with a non-empty code block.",
                    _ev(card, line=line_at(head.start())))], how="citation code block")
        doi = _DOI_RE.search(sec) or _ARXIV_RE.search(sec)
        if doi:
            return _result("card.citation", title, CardStatus.PRESENT, [Fact(
                f"A citation section with {doi.group(0)}.",
                _ev(card, line=line_at(head.start())))], how="DOI or arXiv id")
    bib = _BIBTEX_RE.search(body)
    if bib:
        return _result("card.citation", title, CardStatus.PRESENT, [Fact(
            "A BibTeX entry in the card.", _ev(card, line=line_at(bib.start())))], how="BibTeX")
    first = _CITATION_HEAD_RE.search(body)
    if first:
        heading = first.group(0).lstrip("#").strip()
        return _result("card.citation", title, CardStatus.MISSING, [Fact(
            f"The card has a citation heading ({heading!r}), but no code block, DOI, arXiv id "
            "or BibTeX entry in it (it may point elsewhere for the citation).",
            _ev(card, line=line_at(first.start())))], heading_only=True)
    return _result("card.citation", title, CardStatus.MISSING, [Fact(
        "No citation section with a code block, DOI or arXiv id, and no BibTeX entry.",
        _ev(card))])


def check_stated_source(card: Card, links: list[LinkRef]) -> CheckResult:
    title = "Stated source"
    facts = []
    parents = [str(v) for v in _values(card.metadata.get("source_datasets"))]
    stated = [ln for ln in links if ln.stated]
    for ln in stated:
        facts.append(Fact(f"{ln.label}: {ln.url}", [ln.evidence] if ln.evidence else []))
    if parents:
        facts.append(Fact(f"source_datasets: {', '.join(parents)}.",
                          _ev(card, "source_datasets"), {"source_datasets": parents}))
    if stated or parents:
        return _result("card.stated_source", title, CardStatus.PRESENT, facts,
                       urls=[ln.url for ln in stated], source_datasets=parents)
    return _result("card.stated_source", title, CardStatus.MISSING, [Fact(
        "No source URL (Homepage / Repository / Paper / Point of Contact bullets or URL "
        "metadata) and no source_datasets.", _ev(card))])


def check_card(card: Card, links: list[LinkRef]) -> tuple[list[CheckResult], list[str]]:
    """Returns (results, not-checked notes). A card whose text exists but cannot be read
    (gated) gets no citation result rather than a false `missing`."""
    not_checked: list[str] = []
    if card.text is None and not card.metadata:
        note = card.evidence.note or "no card"
        results = [_result(k, t, CardStatus.MISSING, [Fact(f"No card to read: {note}.",
                                                           [card.evidence])])
                   for k, t in (("card.licence", "Licence field"),
                                ("card.pretty_name", "Dataset name"),
                                ("card.task_categories", "Task categories"),
                                ("card.size_categories", "Size category"),
                                ("card.configs", "Configs / dataset_info"),
                                ("card.citation", "Citation"),
                                ("card.stated_source", "Stated source"))]
        return results, not_checked
    results = [check_licence_field(card)]
    if card.yaml_error:
        results[0].facts.append(Fact(card.yaml_error, _ev(card, line=1)))
    results += check_metadata(card)
    if card.text is None:
        not_checked.append(f"card citation and README source bullets ({card.evidence.note})")
    else:
        results.append(check_citation(card))
    stated = check_stated_source(card, links)
    if card.text is None and stated.status == CardStatus.MISSING:
        pass  # README bullets unreadable: a `missing` here would not be a fact
    else:
        results.append(stated)
    return results, not_checked
