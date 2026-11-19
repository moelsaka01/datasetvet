import json

import pytest

from datasetvet.model import (
    CardStatus,
    CheckResult,
    DatasetRef,
    Evidence,
    Fact,
    Family,
    HealthStatus,
    LicenceStatus,
    LinkStatus,
    Report,
    ScanInfo,
)
from datasetvet.report.json_out import to_json


def test_status_enums_match_plan_section_5_exactly():
    assert [s.value for s in LicenceStatus] == ["consistent", "inconsistent", "missing",
                                                "unknown"]
    assert [s.value for s in CardStatus] == ["present", "missing", "invalid"]
    assert [s.value for s in LinkStatus] == ["ok", "dead", "restricted", "unreachable",
                                             "unknown"]
    assert [s.value for s in HealthStatus] == ["none found", "found", "not checked"]


def test_status_must_belong_to_its_family():
    with pytest.raises(ValueError):
        CheckResult("card.x", Family.CARD, "ok")
    with pytest.raises(ValueError):
        CheckResult("links", Family.LINKS, "safe")
    CheckResult("licence", Family.LICENCE, "unknown")


def test_json_round_trip():
    report = Report(
        dataset=DatasetRef("huggingface", "org/ds", "a" * 40, "hf:org/ds", gated="auto"),
        tool_version="0.0.0",
        scan=ScanInfo(kind="sampled", rows_scanned=10, rows_total=100, seed=3),
        results=[CheckResult("health.pii", Family.HEALTH, HealthStatus.FOUND, "PII",
                             [Fact("x", [Evidence(url="u", lines=[1, 2])], {"n": 1})])],
        not_checked=["licence"],
    )
    text = to_json(report)
    back = Report.from_dict(json.loads(text))
    assert back == report
    assert json.loads(text)["results"][0]["status"] == "found"
    assert json.loads(text)["schema_version"]


def test_scan_header_text():
    assert ScanInfo(kind="full").header() == "Full scan"
    assert ScanInfo(kind="sampled", rows_scanned=1000, rows_total=5000, seed=7).header() == \
        "Sampled: 1,000 of 5,000 rows (seed 7)"
    assert ScanInfo(kind="not checked", reason="gated").header() == "Data not checked: gated"
