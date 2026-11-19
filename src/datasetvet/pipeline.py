"""`datasetvet check`: resolve, card, links, data health -> Report (PLAN.md section 3)."""

from __future__ import annotations

from collections.abc import Callable

from datasetvet import __version__
from datasetvet.checks.card import check_card
from datasetvet.checks.health.runner import run_health
from datasetvet.checks.links import LinkChecker, check_links, missing_file_result
from datasetvet.config import Settings
from datasetvet.http import Http
from datasetvet.hubs.base import Registry
from datasetvet.hubs.huggingface import HuggingFaceAdapter, missing_data_files
from datasetvet.model import Evidence, Report, ScanInfo

NOT_IN_THIS_VERSION = [
    "licence consistency: card vs README text, licence files and sources (planned: Phase 3)",
    "provenance: licences of declared parent datasets (planned: Phase 3)",
]


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
        report.not_checked += NOT_IN_THIS_VERSION
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
