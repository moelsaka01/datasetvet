"""`datasetvet check`: resolve, card, licence, provenance, links, data health -> Report
(PLAN.md section 3)."""

from __future__ import annotations

from collections.abc import Callable

from datasetvet import __version__
from datasetvet.checks.card import check_card
from datasetvet.checks.health.runner import run_health
from datasetvet.checks.licence import (
    CardLicence,
    LicenceContext,
    card_licence,
    card_where,
    check_licence,
)
from datasetvet.checks.links import LinkChecker, check_links, missing_file_result
from datasetvet.checks.provenance import (
    HfParent,
    ProvenanceContext,
    check_provenance,
    mentioned_datasets,
)
from datasetvet.config import Settings
from datasetvet.http import FetchError, Http
from datasetvet.hubs.base import Card, HubAdapter, LinkRef, Registry
from datasetvet.hubs.github import GitHubResolver
from datasetvet.hubs.huggingface import (
    DatasetNotFound,
    HuggingFaceAdapter,
    missing_data_files,
)
from datasetvet.hubs.web import WebResolver
from datasetvet.licences.scanner import get_scanner
from datasetvet.model import DatasetRef, Evidence, Report, ScanInfo


def build_registry(http: Http) -> Registry:
    reg = Registry()
    reg.add_adapter(HuggingFaceAdapter(http))
    return reg


def run_check(ref: str, settings: Settings, *, http: Http | None = None,
              progress: Callable[[str], None] | None = None) -> Report:
    say = progress or (lambda _m: None)
    own_http = http is None
    if http is None:
        http = Http(settings.cache_dir if settings.use_cache else None, host_interval=1.0)
    try:
        adapter = build_registry(http).adapter_for(ref)
        say(f"resolving {ref}")
        ds = adapter.resolve(ref)
        report = Report(dataset=ds, tool_version=__version__, authenticated=http.authenticated,
                        settings=settings.public())
        if ds.disabled:
            report.not_checked.append("everything else: the dataset is disabled on the Hub")
            report.scan = ScanInfo(kind="not checked", reason="dataset disabled on the Hub")
            return report

        say("reading the card")
        card = adapter.card(ds)
        links = adapter.stated_sources(card)
        card_results, card_nc = check_card(card, links)
        report.results += card_results
        report.not_checked += card_nc

        if settings.check_licences:
            run_licences(report, adapter, ds, card, links, http, settings, say)
        else:
            report.not_checked.append("licence consistency and provenance (--no-licence)")

        if settings.check_links:
            say(f"checking {len(links)} link(s)")

            def gated(ds_id: str) -> bool | str | None:
                resp = http.get(f"https://huggingface.co/api/datasets/{ds_id}")
                return resp.json().get("gated") if resp.ok else None

            checker = LinkChecker(http, settings, gated_lookup=gated)
            link_results, link_nc = check_links(links, checker, settings.max_links, say)
            paths = [f.path for f in adapter.files(ds)]
            for config, pattern in missing_data_files(card.metadata.get("configs"), paths):
                ev = Evidence(url=adapter.blob_url(ds, "README.md",
                                                   card.key_lines.get("configs")),
                              revision=ds.revision, path="README.md")
                link_results.append(missing_file_result(pattern, config, ev))
            report.results += link_results
            report.not_checked += link_nc
        else:
            report.not_checked.append("links (--no-links)")

        if settings.check_data:
            say("finding the data files")
            data = adapter.splits(ds, card)
            scan, health = run_health(adapter.fetch, data, settings, say)
            report.scan = scan
            report.results += health
            if data.notes:
                report.settings["data_notes"] = data.notes
            if scan.kind == "not checked":
                report.not_checked.append(f"data health: {scan.reason}")
        else:
            report.scan = ScanInfo(kind="not checked", reason="--no-data given")
            report.not_checked.append("data health (--no-data)")
        report.settings["http_requests"] = http.network_calls
        return report
    finally:
        if own_http:
            http.close()


def run_licences(report: Report, adapter: HubAdapter, ds: DatasetRef, card: Card,
                 links: list[LinkRef], http: Http, settings: Settings,
                 say: Callable[[str], None]) -> None:
    """Licence consistency (5.2) and provenance (5.3); fills report.results and not_checked."""
    scanner = get_scanner(settings.scanner)
    report.scanner = scanner.describe()
    github = GitHubResolver(http)
    report.settings["github"] = "token (GITHUB_TOKEN)" if github.authenticated else "anonymous"
    resolvers = [github, WebResolver(http)] if settings.check_sources else []

    def hf_dataset(ds_id: str) -> tuple[HfParent | None, str]:
        try:
            pds = adapter.resolve(f"hf:{ds_id}")
        except (DatasetNotFound, FetchError, ValueError) as exc:
            return None, str(exc)
        pcard = adapter.card(pds)
        where, ev = card_where(pcard, pds.revision)
        lic = card_licence(pcard.metadata, ev, f"{pds.id} {where}", owner=f"{pds.id}'s card")
        return HfParent(pds.id, pds.revision, lic, adapter.parents(pcard)), ""

    def hf_card(ds_id: str) -> tuple[CardLicence | None, str]:
        parent, note = hf_dataset(ds_id)
        return (parent.licence if parent else None), note

    say("comparing licence claims")
    ctx = LicenceContext(adapter, ds, card, scanner, resolvers, hf_card, say)
    results, nc = check_licence(ctx, links if settings.check_sources else [])
    report.results += results
    report.not_checked += nc
    if not settings.check_sources:
        report.not_checked.append("source licences (--no-sources)")

    parents = adapter.parents(card)
    where, ev = card_where(card, ds.revision)
    child = card_licence(card.metadata, ev, where)
    mentioned = mentioned_datasets(card.body, ds.id, {p.id.lower() for p in parents if p.id})
    if not parents or settings.provenance_depth == 0:
        raw = card.metadata.get("source_datasets")
        why = ("--provenance-depth 0" if parents else
               f"no declared parent datasets (source_datasets: {raw})" if raw else
               "no declared parent datasets (the card has no source_datasets)")
        if mentioned:
            why += (f"; the README mentions {len(mentioned)} other HF dataset(s), not treated "
                    f"as parents: {', '.join(mentioned[:8])}")
        report.not_checked.append(f"provenance: {why}")
        return
    say(f"following {len(parents)} declared parent(s)")
    pctx = ProvenanceContext(ds.id, child, parents, hf_dataset, resolvers, scanner,
                             depth=settings.provenance_depth, say=say)
    presults, pnc = check_provenance(pctx)
    report.results += presults
    report.not_checked += pnc
    if mentioned:
        report.not_checked.append(f"provenance: the README also mentions {len(mentioned)} HF "
                                  f"dataset(s) not declared in source_datasets: "
                                  f"{', '.join(mentioned[:8])}")
