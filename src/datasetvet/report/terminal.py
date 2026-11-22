"""Terminal report (PLAN.md section 7). Task 2.12.

Rendered only from the Report (the same data as the JSON). First line: the scan type and what
was not checked. One block per section: status word, facts as one-line sentences, evidence.
"""

from __future__ import annotations

from collections import Counter

from rich.console import Console
from rich.markup import escape

from datasetvet.model import CheckResult, Family, Report

STYLE = {
    "present": "default", "ok": "default", "none found": "default", "consistent": "default",
    "missing": "yellow", "invalid": "yellow", "dead": "yellow", "found": "yellow",
    "inconsistent": "yellow", "restricted": "cyan", "unreachable": "magenta",
    "unknown": "bright_black", "not checked": "bright_black",
}
SECTIONS = [(Family.CARD, "Card"), (Family.LICENCE, "Licence consistency"),
            (Family.PROVENANCE, "Provenance (declared parents)"), (Family.LINKS, "Links"),
            (Family.HEALTH, "Data health")]


def _mb(n: int | None) -> str:
    return "unknown size" if n is None else f"{n / 1e6:,.1f} MB"


def _status(s: str) -> str:
    return f"[{STYLE.get(s, 'default')}]{s:<12}[/]"


def render(report: Report, console: Console | None = None, *, evidence: bool = True) -> None:
    c = console or Console(highlight=False, soft_wrap=True)
    ds = report.dataset
    scan = report.scan
    c.print(f"[bold]{escape(scan.header())}[/bold]"
            + (f"  [bright_black]({escape(scan.reason)})[/]" if scan.reason and
               scan.kind == "sampled" else ""))
    if scan.large_repo_warning:
        c.print(f"[bright_black]{escape(scan.large_repo_warning)}[/]")
    if report.not_checked:
        c.print("[bright_black]Not checked:[/]")
        for item in report.not_checked:
            c.print(f"[bright_black]  - {escape(item)}[/]")
    c.print()
    c.print(f"[bold]datasetvet {escape(report.tool_version)}[/bold]  {escape(ds.hub)}:"
            f"{escape(ds.id)} @ {ds.revision[:12]}  [bright_black]{escape(ds.url or '')}[/]")
    meta = [f"checked {report.created_at}",
            f"authenticated: {'yes' if report.authenticated else 'no'}",
            f"licence scanner: {report.scanner}"]
    if report.settings.get("github"):
        meta.append(f"GitHub: {report.settings['github']}")
    if ds.gated:
        meta.append(f"gated: {ds.gated}")
    if scan.kind != "not checked":
        meta.append(f"{scan.rows_scanned:,} rows, {_mb(scan.bytes_read)} read from "
                    f"{scan.source} @ {(scan.source_revision or '?')[:12]} "
                    f"in {scan.seconds:.1f} s")
    c.print("[bright_black]" + escape(" | ".join(meta)) + "[/]")
    for note in report.settings.get("data_notes", []):
        c.print(f"[bright_black]Note: {escape(note)}[/]")

    for family, title in SECTIONS:
        results = report.by_family(family)
        if not results:
            continue
        c.print()
        head = title
        if family in (Family.LINKS, Family.LICENCE, Family.PROVENANCE):
            counts = Counter(r.status for r in results)
            head += " (" + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) + ")"
        if family == Family.HEALTH:
            head += f" ({scan.header()})"
        c.print(f"[bold underline]{escape(head)}[/]")
        all_nc = all(r.status == "not checked" for r in results)
        if family == Family.HEALTH and all_nc and scan.kind == "not checked":
            names = ", ".join(r.title.lower() for r in results)
            c.print(f"  {_status('not checked')} {escape(names)}")
            continue
        for r in results:
            _render_result(c, r, family, evidence)
    c.print()
    c.print(f"[bright_black]{escape(report.footer)}[/]")


def _render_result(c: Console, r: CheckResult, family: Family, evidence: bool) -> None:
    if family == Family.LINKS:
        fact = r.facts[0] if r.facts else None
        c.print(f"  {_status(r.status)} {escape(r.title)}: "
                f"{escape(fact.text if fact else '')}")
        if evidence and fact and fact.evidence and fact.evidence[0].url and \
                r.data.get("url") is not None:
            c.print(f"  {'':<12} [bright_black]stated at {escape(fact.evidence[0].url)}[/]")
        return
    c.print(f"  {_status(r.status)} [bold]{escape(r.title)}[/bold]")
    for f in r.facts:
        c.print(f"  {'':<12} {escape(f.text)}")
        if evidence:
            for e in f.evidence[:1]:
                if e.url:
                    c.print(f"  {'':<12} [bright_black]{escape(e.url)}"
                            + (f" ({escape(e.note)})" if e.note else "") + "[/]")
