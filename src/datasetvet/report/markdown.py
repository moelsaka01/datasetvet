"""Markdown report, for PRs, issues and GitHub job summaries (PLAN.md section 7, task 5.1).

Rendered only from the Report, like the JSON and the terminal view, so the three cannot
disagree. Facts only: statuses are the closed sets of PLAN.md section 5; nothing here is a
verdict. Text that comes from a dataset (file names, masked examples) is escaped, so it cannot
turn into markup.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from datasetvet.model import CheckResult, Family, Report

SECTIONS = [(Family.CARD, "Card"), (Family.LICENCE, "Licence consistency"),
            (Family.PROVENANCE, "Provenance (declared parents)"), (Family.LINKS, "Links"),
            (Family.HEALTH, "Data health")]
_SPECIAL = re.compile(r"([\\`*\[\]<|#~]|(?<![A-Za-z0-9])_|_(?![A-Za-z0-9]))")


def esc(text: str) -> str:
    """Escape markdown and HTML specials (an underscore inside a word is left alone); one line."""
    return _SPECIAL.sub(lambda m: "\\" + m.group(1), " ".join(str(text).split()))


def _link(url: str, label: str = "evidence") -> str:
    safe = url.replace(" ", "%20").replace(")", "%29").replace("(", "%28")
    return f"[{esc(label)}]({safe})" if safe.startswith(("https://", "http://")) else esc(url)


def _counts(results: list[CheckResult]) -> str:
    """Status counts of the comparisons; the licence summary is named apart, not counted."""
    overall = next((r for r in results if r.check == "licence.summary"), None)
    rest = Counter(r.status for r in results if r.check != "licence.summary")
    text = ", ".join(f"{n} {s}" for s, n in sorted(rest.items()))
    return f"overall {overall.status}; comparisons: {text}" if overall else text


def _result(r: CheckResult, family: Family) -> list[str]:
    if family == Family.LINKS:
        fact = r.facts[0] if r.facts else None
        line = f"- `{r.status}` {esc(r.title)}: {esc(fact.text) if fact else ''}"
        return [line]
    lines = [f"- `{r.status}` **{esc(r.title)}**"]
    for f in r.facts:
        text = f"  - {esc(f.text)}"
        url = next((e.url for e in f.evidence if e.url), None)
        if url:
            e = next(e for e in f.evidence if e.url == url)
            text += f" ({_link(url, 'evidence')}{', ' + esc(e.note) if e.note else ''})"
        lines.append(text)
    return lines


def to_markdown(report: Report) -> str:
    ds, scan = report.dataset, report.scan
    out = [f"# datasetvet: {esc(ds.hub)}:{esc(ds.id)} @ {ds.revision[:12]}", ""]
    meta = [f"datasetvet {esc(report.tool_version)}", f"checked {esc(report.created_at)}",
            f"authenticated: {'yes' if report.authenticated else 'no'}",
            f"licence scanner: {esc(report.scanner)}"]
    if ds.url:
        meta.insert(0, _link(ds.url, "dataset at this revision"))
    out += [f"**{esc(scan.header())}**", "", " · ".join(meta), ""]
    if scan.large_repo_warning:
        out += [f"> {esc(scan.large_repo_warning)}", ""]
    if report.not_checked:
        out += ["**Not checked**", ""] + [f"- {esc(n)}" for n in report.not_checked] + [""]
    summary = []
    for family, title in SECTIONS:
        results = report.by_family(family)
        if results:
            n = sum(r.check != "licence.summary" for r in results)
            summary.append(f"| {title} | {n} | {_counts(results)} |")
    if summary:
        out += ["| section | results | statuses |", "|---|---|---|", *summary, ""]
    for family, title in SECTIONS:
        results = report.by_family(family)
        if not results:
            continue
        out += [f"## {title}", ""]
        for r in results:
            out += _result(r, family)
        out.append("")
    out += ["---", f"*{esc(report.footer)}*", ""]
    return "\n".join(out)


def write_markdown(report: Report, path: str | Path) -> None:
    Path(path).write_text(to_markdown(report), encoding="utf-8", newline="\n")
