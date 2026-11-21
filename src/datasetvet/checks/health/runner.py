"""One streaming pass over the data, then the data-health check results (PLAN.md 5.5).

For every chunk: row/input hashes into DuckDB, empty rows, label counts, PII pattern matches.
Afterwards: duplicate and leakage queries. Every result says "Full scan" or "Sampled", and
under sampling duplicate/leakage counts are lower bounds ("at least").
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa

from datasetvet.checks.health.duplicates import HashStore
from datasetvet.checks.health.empty import (
    KIND_LABELS,
    EmptyCounter,
    UnreadableFile,
    classify_error,
)
from datasetvet.checks.health.fetching import Fetcher
from datasetvet.checks.health.labels import (
    LabelCounter,
    labels_from_hf_features,
    pick_label_columns,
)
from datasetvet.checks.health.pii import PiiScanner
from datasetvet.checks.health.rowhash import COLLISION_NOTE, hash_columns
from datasetvet.checks.health.scan import ScanPlan, iter_split, plan_scan
from datasetvet.checks.health.values import batch_to_pydict
from datasetvet.config import Settings
from datasetvet.hubs.base import DataPlan, SplitFile, SplitSource
from datasetvet.model import CheckResult, Evidence, Fact, Family, HealthStatus, ScanInfo

Progress = Callable[[str], None]
HEALTH_CHECKS = {
    "health.duplicates": "Duplicate rows within a split",
    "health.leakage": "Leakage across splits",
    "health.empty": "Empty rows",
    "health.unreadable": "Files that could not be read as rows",
    "health.labels": "Label columns",
    "health.pii": "PII pattern matches",
}


@dataclass
class SplitState:
    split: SplitSource
    rows: int = 0
    label_cols: list[str] | None = None
    label_how: str = ""
    labels: dict[str, LabelCounter] = field(default_factory=dict)
    empty: EmptyCounter = field(default_factory=EmptyCounter)
    pii: PiiScanner = field(default_factory=PiiScanner)
    files_read: int = 0
    bytes_read: int = 0


def not_checked_results(reason: str) -> list[CheckResult]:
    return [CheckResult(check=k, family=Family.HEALTH, status=HealthStatus.NOT_CHECKED,
                        title=t, facts=[Fact(f"Not checked: {reason}.")])
            for k, t in HEALTH_CHECKS.items()]


def run_health(fetch: Callable[[SplitFile, Path], Path], data: DataPlan, settings: Settings,
               progress: Progress | None = None, fetch_stats: dict[str, Any] | None = None,
               ) -> tuple[ScanInfo, list[CheckResult]]:
    """Scan the data. `fetch_stats`, if given, receives how the files were fetched (git /
    HTTP counts); it never changes the results."""
    say = progress or (lambda _m: None)
    if data.not_checked:
        info = ScanInfo(kind="not checked", reason=data.not_checked)
        return info, not_checked_results(data.not_checked)
    splits = data.splits
    if settings.configs:
        splits = [s for s in splits if s.config in settings.configs]
        if not splits:
            reason = f"none of the requested configs {settings.configs} exist"
            return ScanInfo(kind="not checked", reason=reason), not_checked_results(reason)
    plan = plan_scan(splits, max_scan_bytes=settings.max_scan_bytes,
                     sample_rows=settings.sample_rows, seed=settings.seed,
                     force_full=settings.full, max_download_bytes=settings.max_download_bytes)
    started = time.monotonic()
    unreadable: list[UnreadableFile] = []
    states: list[SplitState] = []
    with tempfile.TemporaryDirectory(prefix="datasetvet-") as tmp:
        tmpdir = Path(tmp)
        store = HashStore(tmpdir, settings.duckdb_memory)
        fetcher = Fetcher(fetch, splits, plan, tmpdir, workers=settings.fetch_workers,
                          git=data.git, use_git=settings.git_fetch, say=say)
        try:
            for split in splits:
                st = SplitState(split, pii=PiiScanner(region=settings.phone_region))
                states.append(st)
                _scan_split(st, plan, fetcher, tmpdir, store, unreadable, say)
            say("comparing row hashes")
            dups = store.duplicates()
            leaks = store.leakage()
        finally:
            fetcher.close()
            store.close()
            if fetch_stats is not None:
                fetch_stats.update(fetcher.stats)
    seconds = time.monotonic() - started
    rows = sum(s.rows for s in states)
    if plan.capped:
        unread = sorted({st.split.key for st in states if st.rows == 0})
        plan.reason = (plan.reason or "") + (
            f"; download cap reached: {len(plan.capped)} file(s) not read"
            + (f", so {len(unread)} split(s) have no rows in the sample: "
               + ", ".join(unread[:10]) + (" ..." if len(unread) > 10 else "")
               if unread else ""))
    info = ScanInfo(
        kind=plan.mode, rows_scanned=rows,
        rows_total=plan.rows_total if plan.rows_total is not None else (
            rows if plan.mode == "full" and not unreadable else None),
        bytes_total=plan.bytes_total, bytes_read=sum(s.bytes_read for s in states),
        seed=plan.seed if plan.mode == "sampled" else None,
        source=splits[0].source if splits else None,
        source_revision=splits[0].revision if splits else None,
        reason=plan.reason, seconds=round(seconds, 2), partial=bool(unreadable),
        listing_complete=data.listing_complete,
    )
    results = [
        _dup_result(dups, states, plan),
        _leak_result(leaks, states, plan),
        _empty_result(states, plan),
        _unreadable_result(unreadable),
        _labels_result(states, plan),
        _pii_result(states, plan),
    ]
    for r in results:
        r.data["scan"] = info.header()
        if unreadable and r.check != "health.unreadable":
            r.data["partial"] = True
    return info, results


def _scan_split(st: SplitState, plan: ScanPlan, fetch, tmpdir: Path, store: HashStore,
                unreadable: list[UnreadableFile], say: Progress) -> None:
    split = st.split
    quota = plan.quotas.get(split.key)
    say(f"reading {split.key} ({len(split.files)} file(s)"
        + (f", sample quota {quota:,} rows" if quota else "") + ")")

    def on_error(f: SplitFile, exc: BaseException) -> None:
        unreadable.append(UnreadableFile(split.key, f.path, f"{type(exc).__name__}: {exc}"[:300],
                                         classify_error(exc)))

    def on_file(_f: SplitFile, size: int) -> None:
        st.files_read += 1
        st.bytes_read += size

    for chunk in iter_split(split, plan, fetch, tmpdir, on_error, on_file):
        batch = chunk.batch
        names = batch.schema.names
        if st.label_cols is None:
            classlabels = labels_from_hf_features(chunk.hf_metadata) or split.label_names
            st.label_cols, st.label_how = pick_label_columns(names, classlabels)
            for c in st.label_cols:
                st.labels[c] = LabelCounter(names=classlabels.get(c))
        try:
            cols = batch_to_pydict(batch)
            row_h, input_h = hash_columns(cols, st.label_cols)
        except (pa.ArrowException, ValueError, TypeError, OverflowError) as exc:
            # a batch that cannot be turned into values stops that file, not the dataset
            if not any(u.split == split.key and u.path == chunk.file_path for u in unreadable):
                on_error(split.files[chunk.file_no], exc)
            continue
        store.add(split.key, split.config, chunk.file_no, chunk.first_row, row_h, input_h)
        st.empty.add_columns(cols, chunk.file_no, chunk.first_row)
        for c in st.label_cols:
            if c in names:
                st.labels[c].add(batch.column(c))
        for i, field_ in enumerate(batch.schema):
            st.pii.add(field_.name, batch.column(i))
        st.rows += batch.num_rows


# -- result builders ----------------------------------------------------------------------

def _loc(st: SplitState, file_no: int, row: int) -> str:
    if len(st.split.files) == 1:
        return f"row {row}"
    return f"{st.split.files[file_no].path} row {row}"


def _split_evidence(st: SplitState) -> list[Evidence]:
    files = st.split.files
    if not files:
        return []
    note = f"{st.split.source}, {len(files)} file(s)"
    return [Evidence(url=files[0].url if len(files) == 1 else _dir_url(files[0].url),
                     revision=st.split.revision, note=note)]


def _dir_url(url: str) -> str:
    return url.rsplit("/", 1)[0].replace("/resolve/", "/tree/", 1)


def _pct(n: int, total: int) -> str:
    return f"{100.0 * n / total:.2f}%" if total else "n/a"


def _least(plan: ScanPlan) -> str:
    return "at least " if plan.mode == "sampled" else ""


def _dup_result(dups, states: list[SplitState], plan: ScanPlan) -> CheckResult:
    by_key = {s.split.key: s for s in states}
    facts = []
    found = False
    for d in dups:
        st = by_key[d.split]
        if d.extra_copies:
            found = True
            ex = "; ".join(" = ".join(_loc(st, f, r) for f, r in grp) for grp in d.examples)
            facts.append(Fact(
                f"{d.split}: {_least(plan)}{d.extra_copies:,} extra copies of rows already in "
                f"the split ({_pct(d.extra_copies, d.rows)} of {d.rows:,} rows scanned). "
                f"Examples: {ex}.",
                _split_evidence(st), {"split": d.split, "extra_copies": d.extra_copies,
                                      "rows": d.rows, "examples": d.examples}))
        else:
            facts.append(Fact(f"{d.split}: no duplicate rows in {d.rows:,} rows scanned.",
                              _split_evidence(st), {"split": d.split, "extra_copies": 0,
                                                    "rows": d.rows}))
    facts.append(Fact(f"Rows are equal when every column is equal; {COLLISION_NOTE}."))
    return CheckResult("health.duplicates", Family.HEALTH,
                       HealthStatus.FOUND if found else HealthStatus.NONE_FOUND,
                       HEALTH_CHECKS["health.duplicates"], facts)


def _unlabelled(st: SplitState) -> bool:
    """True when every label value in the split is the ClassLabel 'no label' -1 or null."""
    if not st.labels:
        return False
    return all(lc.counts and set(lc.counts) <= lc.no_label_values()
               for lc in st.labels.values())


def _leak_result(leaks, states: list[SplitState], plan: ScanPlan) -> CheckResult:
    by_key = {s.split.key: s for s in states}
    facts = []
    found = False
    for lk in leaks:
        a, b = by_key[lk.split_a], by_key[lk.split_b]
        if not lk.shared_inputs:
            facts.append(Fact(f"{lk.split_a} and {lk.split_b}: no shared inputs.",
                              data={"pair": [lk.split_a, lk.split_b], "shared_inputs": 0}))
            continue
        found = True
        ex = "; ".join(f"{_loc(a, *e['a'])} = {_loc(b, *e['b'])}" for e in lk.examples)
        labels = ""
        compare_labels = bool(a.label_cols) and not _unlabelled(a) and not _unlabelled(b)
        if compare_labels:
            labels = (f" {lk.label_differs:,} of these inputs appear with different labels "
                      "in the two splits.")
        elif a.label_cols:
            which = lk.split_a if _unlabelled(a) else lk.split_b
            labels = (f" {which} has no labels (all null, or -1 for a ClassLabel), so labels "
                      "are not compared.")
        facts.append(Fact(
            f"{lk.split_a} and {lk.split_b}: {_least(plan)}{lk.shared_inputs:,} distinct inputs "
            f"appear in both ({lk.rows_a:,} rows in {lk.split_a}, {lk.rows_b:,} rows in "
            f"{lk.split_b}; {lk.pct_of_smaller:.2f}% of {lk.smaller}).{labels} Examples: {ex}.",
            _split_evidence(a) + _split_evidence(b),
            {"pair": [lk.split_a, lk.split_b], "shared_inputs": lk.shared_inputs,
             "rows_a": lk.rows_a, "rows_b": lk.rows_b, "pct_of_smaller": lk.pct_of_smaller,
             "label_differs": lk.label_differs if compare_labels else None,
             "examples": lk.examples}))
    configs = {s.split.config for s in states}
    for cfg in sorted(configs):
        n = sum(1 for s in states if s.split.config == cfg)
        if n < 2:
            facts.append(Fact(f"Config {cfg} has one split; there is nothing to compare."))
    label_how = sorted({f"{s.split.key}: {', '.join(s.label_cols)} ({s.label_how})"
                        for s in states if s.label_cols})
    facts.append(Fact(
        "Inputs are compared without label columns"
        + (f" ({'; '.join(label_how)})." if label_how else
           "; no label column was identified, so inputs are whole rows.")))
    status = HealthStatus.FOUND if found else HealthStatus.NONE_FOUND
    return CheckResult("health.leakage", Family.HEALTH, status, HEALTH_CHECKS["health.leakage"],
                       facts)


def _empty_result(states: list[SplitState], plan: ScanPlan) -> CheckResult:
    facts = []
    found = False
    for st in states:
        e = st.empty
        if e.count:
            found = True
            ex = ", ".join(_loc(st, f, r) for f, r in e.examples)
            facts.append(Fact(f"{st.split.key}: {e.count:,} empty rows "
                              f"({_pct(e.count, st.rows)} of {st.rows:,}). Examples: {ex}.",
                              _split_evidence(st), {"split": st.split.key, "count": e.count}))
        else:
            facts.append(Fact(f"{st.split.key}: no empty rows in {st.rows:,} rows scanned.",
                              data={"split": st.split.key, "count": 0}))
    return CheckResult("health.empty", Family.HEALTH,
                       HealthStatus.FOUND if found else HealthStatus.NONE_FOUND,
                       HEALTH_CHECKS["health.empty"], facts)


def _unreadable_result(unreadable: list[UnreadableFile]) -> CheckResult:
    title = HEALTH_CHECKS["health.unreadable"]
    if not unreadable:
        return CheckResult("health.unreadable", Family.HEALTH, HealthStatus.NONE_FOUND, title,
                           [Fact("Every file that was read could be read as rows.")])
    facts = [Fact(f"{c.split}: {c.path} could not be read as rows ({KIND_LABELS[c.kind]}: "
                  f"{c.error}). This does not by itself mean the file is damaged. The split's "
                  "other results are partial.",
                  data={"split": c.split, "path": c.path, "error": c.error, "kind": c.kind})
             for c in unreadable]
    return CheckResult("health.unreadable", Family.HEALTH, HealthStatus.FOUND, title, facts)


def _labels_result(states: list[SplitState], plan: ScanPlan) -> CheckResult:
    facts = []
    any_cols = False
    by_cfg: dict[str, dict[str, SplitState]] = {}
    for st in states:
        by_cfg.setdefault(st.split.config, {})[st.split.split] = st
        if not st.label_cols:
            continue
        any_cols = True
        for col, lc in st.labels.items():
            if lc.too_many:
                facts.append(Fact(f"{st.split.key}: column {col} has more than 1,000 distinct "
                                  "values; not tabulated.", data={"split": st.split.key,
                                                                  "column": col}))
                continue
            table = lc.table()
            shown = ", ".join(f"{t['label']} {t['count']:,} ({100 * t['share']:.1f}%)"
                              for t in table[:12])
            more = f", and {len(table) - 12} more" if len(table) > 12 else ""
            ratio = lc.ratio()
            ratio_txt = f" Largest/smallest label count: {ratio:.2f}." if ratio else ""
            facts.append(Fact(f"{st.split.key}, column {col}: {shown}{more}.{ratio_txt}",
                              data={"split": st.split.key, "column": col, "table": table,
                                    "max_min_ratio": ratio, "how": st.label_how}))
    for cfg, by_split in by_cfg.items():
        train = by_split.get("train")
        if not train or not train.label_cols:
            continue
        for name, st in by_split.items():
            if name == "train":
                continue
            for col, lc in st.labels.items():
                tr = train.labels.get(col)
                if not tr or tr.too_many or lc.too_many:
                    continue
                missing = [lc.display(k) for k in lc.counts
                           if k not in tr.counts and k not in lc.no_label_values()]
                if missing:
                    facts.append(Fact(
                        f"{cfg}/{name}, column {col}: labels absent from train"
                        f"{' (in the sample)' if plan.mode == 'sampled' else ''}: "
                        f"{', '.join(missing[:20])}.",
                        data={"split": f"{cfg}/{name}", "column": col,
                              "absent_from_train": missing}))
    if any_cols and plan.mode == "sampled":
        sizes = sorted({c for c in (plan.chunk_rows(s.split.key) for s in states) if c})
        size = f"{sizes[-1]}" if len(sizes) == 1 else f"{sizes[0]}-{sizes[-1]}" if sizes \
            else "?"
        facts.append(Fact(
            f"Counts are for the sample only. Rows were read in chunks of up to {size} rows "
            "spread across each file read, but not every file is read, so if the files are "
            "ordered (e.g. one label per file) the shares can differ from the full data.",
            data={"chunk_rows": sizes}))
    if not any_cols:
        return CheckResult("health.labels", Family.HEALTH, HealthStatus.NOT_CHECKED,
                           HEALTH_CHECKS["health.labels"],
                           [Fact("No label column identified (no ClassLabel feature and no "
                                 "column named label/labels).")])
    return CheckResult("health.labels", Family.HEALTH, HealthStatus.FOUND,
                       HEALTH_CHECKS["health.labels"], facts)


def _pii_result(states: list[SplitState], plan: ScanPlan) -> CheckResult:
    facts = []
    found = False
    scanned_any = False
    region = states[0].pii.region if states else None
    for st in states:
        if st.pii.columns:
            scanned_any = True
        for col, m in st.pii.columns.items():
            parts = []
            if m.values_with_email:
                parts.append(f"{m.values_with_email:,} values match the email pattern "
                             f"(e.g. {', '.join(m.email_examples)})")
            if m.values_with_phone:
                parts.append(f"{m.values_with_phone:,} values match the phone pattern "
                             f"(e.g. {', '.join(m.phone_examples)})")
            if parts:
                found = True
                facts.append(Fact(f"{st.split.key}, column {col}: " + "; ".join(parts) + ".",
                                  data={"split": st.split.key, "column": col,
                                        "email_values": m.values_with_email,
                                        "phone_values": m.values_with_phone}))
    if not scanned_any:
        return CheckResult("health.pii", Family.HEALTH, HealthStatus.NOT_CHECKED,
                           HEALTH_CHECKS["health.pii"], [Fact("No string columns to scan.")])
    phone = (f"phone: international +numbers and {region} national formats" if region
             else "phone: international +numbers only (add --phone-region XX for national "
                  "formats)")
    facts.append(Fact(f"These are pattern matches, not a finding of personal data. Patterns: "
                      f"email; {phone}. Examples are masked."))
    return CheckResult("health.pii", Family.HEALTH,
                       HealthStatus.FOUND if found else HealthStatus.NONE_FOUND,
                       HEALTH_CHECKS["health.pii"], facts)


def summary_counts(results: list[CheckResult]) -> dict[str, Any]:
    return {r.check: r.status for r in results}
