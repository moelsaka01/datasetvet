"""Phase 5.5: held-out draw, baselines A and B, the sheet guard and the scorer (PLAN.md 8.1)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "eval" / "holdout"))

import draw
import predict
import score


def test_draw_is_seeded_and_excludes_dpi_and_gone():
    items = [{"id": f"Org/D{i}"} for i in range(30)] + [{"id": "KakologArchives/KakologArchives"}]
    pool = draw.population(items, dpi={"org/d3", "org/d7"})
    ids = {d["id"] for d in pool}
    assert "Org/D3" not in ids and "Org/D7" not in ids
    assert "KakologArchives/KakologArchives" not in ids and len(pool) == 28
    assert [d["id"] for d in pool] == sorted(ids, key=str.lower)
    assert draw.draw(pool, 20261122, 10) == draw.draw(pool, 20261122, 10)
    assert draw.draw(pool, 20261122, 10) != draw.draw(pool, 20261123, 10)


def test_urls_in_card_are_raw_and_deduplicated():
    text = "See [paper](https://arxiv.org/abs/1.2). Code: https://github.com/o/r. " \
           "Again https://github.com/o/r and <https://x.org/a>"
    assert draw.urls_in(text) == ["https://arxiv.org/abs/1.2", "https://github.com/o/r",
                                  "https://x.org/a"]


def test_baseline_a_is_the_tag_alone():
    assert predict.baseline_a([]) == "missing"
    assert predict.baseline_a(["license:unknown"]) == "missing"
    assert predict.baseline_a(["license:mit", "task_categories:x"]) == "consistent"
    assert predict.baseline_a(["license:other"]) == "consistent"


def test_baseline_b_compares_detected_keys_with_the_tag():
    assert predict.baseline_b([], ["MIT"]) == "missing"
    assert predict.baseline_b(["license:mit"], []) == "unknown"
    assert predict.baseline_b(["license:mit"], ["MIT", "MIT"]) == "consistent"
    assert predict.baseline_b(["license:mit"], ["MIT", "Apache-2.0"]) == "inconsistent"
    assert predict.baseline_b(["license:cc-by-4.0", "license:mit"],
                              ["MIT", "CC-BY-4.0"]) == "consistent"
    assert predict.baseline_b(["license:apache-2.0"], ["LicenseRef-scancode-x"]) == \
        "inconsistent"


def sheet(**labels):
    base = {"row": "1", "hf_id": "o/d", "frozen_sha": "abc", "gated": "no"}
    return dict(base, expert_licences=labels.get("expert", ""),
                expected_status=labels.get("status", ""), confidence="", notes="")


def test_sheet_guard_needs_every_label_and_unchanged_columns():
    tagged = [sheet()]
    assert predict.check_sheet([sheet(status="consistent", expert="MIT")], tagged) == []
    assert predict.check_sheet([sheet(status="excluded: expert none")], tagged) == []
    assert "empty" in predict.check_sheet([sheet()], tagged)[0]
    assert "unknown expected_status" in predict.check_sheet([sheet(status="ok")], tagged)[0]
    changed = dict(sheet(status="missing"), frozen_sha="def")
    assert "differ from the tagged sheet" in predict.check_sheet([changed], tagged)[0]


def test_sheet_saved_by_excel_with_a_bom_still_reads():
    text = "row,hf_id\r\n1,o/d\r\n"
    assert predict.read_sheet("﻿" + text) == predict.read_sheet(text) == \
        [{"row": "1", "hf_id": "o/d"}]


def test_mcnemar_exact_known_value():
    x = [True] * 10 + [False] * 2 + [True] * 5
    y = [False] * 10 + [True] * 2 + [True] * 5
    m = score.mcnemar_exact(x, y)
    assert (m["x_only"], m["y_only"]) == (10, 2)
    assert m["p"] == pytest.approx(2 * (1 + 12 + 66) / 4096)
    assert score.mcnemar_exact([True], [True])["p"] == 1.0


def test_bootstrap_is_seeded():
    pairs = [("consistent", "consistent")] * 20 + [("inconsistent", "inconsistent")] * 5 + \
        [("inconsistent", "consistent")] * 5 + [("missing", "missing")] * 10 + \
        [("consistent", "unknown")] * 3
    a = score.bootstrap_kappa(pairs, n=500)
    assert a == score.bootstrap_kappa(pairs, n=500)
    lo, hi = a["ci95"]
    assert lo < score.kappa_decided(pairs) < hi


def pred(expected, a, b, c, sub=None):
    return {"batch": "holdout-v1", "hf_id": "x", "expected": expected, "A": a, "B": b, "C": c,
            "C_sub": sub}


def test_score_excludes_and_checks_the_goal():
    preds = ([pred("consistent", "consistent", "unknown", "consistent", "confirmed")] * 40
             + [pred("inconsistent", "consistent", "unknown", "inconsistent")] * 15
             + [pred("missing", "missing", "missing", "missing")] * 10
             + [pred("excluded: expert none", "missing", "missing", "missing")] * 5
             + [dict(pred("consistent", "consistent", "consistent", "consistent"),
                     excluded="card not readable")])
    out = score.score(preds)
    assert out["scored"] == 65 and out["excluded"]["excluded: expert none"] == 5
    c = out["configurations"]["C"]
    assert c["agree"] == 65 and c["kappa_decided"] == pytest.approx(1.0)
    assert out["paired"]["C vs A"] == {"x_only": 15, "y_only": 0,
                                       "p": pytest.approx(2 / 2 ** 15)}
    assert out["goal"]["beats_A"] and out["goal"]["beats_B"] and out["goal"]["met"]
    assert out["configurations"]["A"]["confusion"]["inconsistent"]["consistent"] == 15
    assert not out["too_few_rows"]


def test_score_reports_a_miss():
    preds = [pred("consistent", "consistent", "consistent", "unknown")] * 30 + \
        [pred("missing", "missing", "missing", "missing")] * 30
    out = score.score(preds)
    assert not out["goal"]["abstention_below_15pct"] and not out["goal"]["beats_A"]
    assert not out["goal"]["met"]
