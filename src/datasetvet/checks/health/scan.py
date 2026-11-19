"""Scan planner and streaming reader: full scan or deterministic sample (PLAN.md 5.5). Task 2.8.

- Total bytes <= max_scan_bytes (default 5 GB), or --full: **Full scan**, every row of every
  split, files read in path order.
- Above the limit: **deterministic sample** of up to `sample_rows` rows. Each split gets a
  quota proportional to its rows (bytes when rows are unknown). Within a split, files are
  visited in an order shuffled with the seed, and whole Parquet row groups are taken in a
  seeded order until the quota is met (the last group is cut at the quota). CSV/JSON Lines
  files have no row groups, so their first rows are read.
- Files are downloaded one at a time to a temp dir and deleted after reading, so disk use is
  bounded by the largest file.
"""

from __future__ import annotations

import gzip
import json
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.json as pajson
import pyarrow.parquet as papq

from datasetvet.hubs.base import SplitFile, SplitSource

BATCH_ROWS = 4096


@dataclass
class ScanPlan:
    mode: str  # "full" or "sampled"
    seed: int
    bytes_total: int | None
    rows_total: int | None
    sample_rows: int | None = None
    quotas: dict[str, int | None] = field(default_factory=dict)  # split key -> row quota
    reason: str | None = None

    def header(self, rows_scanned: int) -> str:
        if self.mode == "full":
            return "Full scan"
        total = f"{self.rows_total:,}" if self.rows_total is not None else "unknown"
        return f"Sampled: {rows_scanned:,} of {total} rows (seed {self.seed})"


def plan_scan(splits: list[SplitSource], *, max_scan_bytes: int, sample_rows: int, seed: int,
              force_full: bool = False) -> ScanPlan:
    bytes_total = sum(s.bytes or 0 for s in splits) if splits else 0
    known_rows = [s.rows for s in splits]
    rows_total = sum(r for r in known_rows if r is not None) \
        if all(r is not None for r in known_rows) else None
    if force_full or bytes_total <= max_scan_bytes:
        reason = "--full given" if force_full and bytes_total > max_scan_bytes else None
        return ScanPlan("full", seed, bytes_total, rows_total,
                        quotas={s.key: None for s in splits}, reason=reason)
    quotas: dict[str, int | None] = {}
    if rows_total:
        weights = {s.key: (s.rows or 0) / rows_total for s in splits}
    else:
        weights = {s.key: (s.bytes or 0) / bytes_total for s in splits}
    for s in splits:
        q = max(1, round(sample_rows * weights[s.key]))
        if s.rows is not None:
            q = min(q, s.rows)
        quotas[s.key] = q
    reason = (f"{bytes_total:,} bytes is above the full-scan limit of {max_scan_bytes:,} bytes; "
              "use --full to scan everything")
    return ScanPlan("sampled", seed, bytes_total, rows_total, sample_rows=sample_rows,
                    quotas=quotas, reason=reason)


def file_order(split: SplitSource, plan: ScanPlan) -> list[int]:
    idx = list(range(len(split.files)))
    if plan.mode == "sampled":
        random.Random(f"{plan.seed}:{split.key}:files").shuffle(idx)
    return idx


def row_group_order(n_groups: int, split: SplitSource, f: SplitFile, plan: ScanPlan) -> list[int]:
    idx = list(range(n_groups))
    if plan.mode == "sampled":
        random.Random(f"{plan.seed}:{split.key}:{f.path}:groups").shuffle(idx)
    return idx


@dataclass
class Chunk:
    """A batch of rows plus where it came from (file index in the split, first row in file)."""

    batch: pa.RecordBatch
    file_no: int
    file_path: str
    first_row: int
    hf_metadata: dict | None = None


def hf_features(schema: pa.Schema) -> dict | None:
    meta = schema.metadata or {}
    raw = meta.get(b"huggingface")
    if not raw:
        return None
    try:
        return json.loads(raw).get("info", {}).get("features")
    except (ValueError, AttributeError):
        return None


def _read_parquet(path: Path, split: SplitSource, f: SplitFile, file_no: int, plan: ScanPlan,
                  budget: int | None) -> Iterator[Chunk]:
    with papq.ParquetFile(path) as pf:
        yield from _read_parquet_groups(pf, split, f, file_no, plan, budget)


def _read_parquet_groups(pf: papq.ParquetFile, split: SplitSource, f: SplitFile, file_no: int,
                         plan: ScanPlan, budget: int | None) -> Iterator[Chunk]:
    feats = hf_features(pf.schema_arrow)
    md = pf.metadata
    starts = []
    acc = 0
    for g in range(md.num_row_groups):
        starts.append(acc)
        acc += md.row_group(g).num_rows
    left = budget
    for g in row_group_order(md.num_row_groups, split, f, plan):
        if left is not None and left <= 0:
            return
        offset = starts[g]
        rg = md.row_group(g)
        avg = rg.total_byte_size / rg.num_rows if rg.num_rows else 0
        # keep each batch near 64 MB in memory, even for image or audio rows
        size = int(max(16, min(BATCH_ROWS, (64 << 20) / avg))) if avg else BATCH_ROWS
        for batch in pf.iter_batches(batch_size=size, row_groups=[g]):
            if left is not None:
                if left <= 0:
                    return
                if batch.num_rows > left:
                    batch = batch.slice(0, left)
                left -= batch.num_rows
            yield Chunk(batch, file_no, f.path, offset, feats)
            offset += batch.num_rows


def _open_text(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rb")
    return open(path, "rb")


def _read_tabular(path: Path, f: SplitFile, file_no: int, budget: int | None) -> Iterator[Chunk]:
    fmt = f.fmt
    if fmt in ("csv", "tsv"):
        opts = pacsv.ParseOptions(delimiter="\t" if fmt == "tsv" else ",")
        fh = _open_text(path)
        try:
            reader = pacsv.open_csv(fh, parse_options=opts,
                                    read_options=pacsv.ReadOptions(block_size=1 << 22))
            yield from _limit(iter(reader), file_no, f.path, budget)
        finally:
            fh.close()
        return
    if fmt in ("jsonl", "json"):
        with _open_text(path) as fh:
            head = fh.read(64).lstrip()
        if head.startswith(b"["):
            with _open_text(path) as fh:
                rows = json.load(fh)
            if not isinstance(rows, list):
                raise ValueError("JSON file is not a list of records")
            batches = iter(pa.Table.from_pylist(rows).to_batches(BATCH_ROWS))
        else:
            with _open_text(path) as fh:
                table = pajson.read_json(fh, read_options=pajson.ReadOptions(block_size=1 << 22))
            batches = iter(table.to_batches(BATCH_ROWS))
    else:
        raise ValueError(f"unsupported format {fmt!r}")
    yield from _limit(batches, file_no, f.path, budget)


def _limit(batches: Iterator[pa.RecordBatch], file_no: int, path: str,
           budget: int | None) -> Iterator[Chunk]:
    offset = 0
    left = budget
    for batch in batches:
        if left is not None:
            if left <= 0:
                return
            if batch.num_rows > left:
                batch = batch.slice(0, left)
            left -= batch.num_rows
        yield Chunk(batch, file_no, path, offset, None)
        offset += batch.num_rows


def iter_split(split: SplitSource, plan: ScanPlan, fetch: Callable[[SplitFile, Path], Path],
               tmpdir: Path, on_error: Callable[[SplitFile, BaseException], None],
               on_file: Callable[[SplitFile, int], None] | None = None) -> Iterator[Chunk]:
    """Yield chunks for one split. Errors on a file are reported via on_error and skipped."""
    quota = plan.quotas.get(split.key)
    taken = 0
    for file_no in file_order(split, plan):
        if quota is not None and taken >= quota:
            return
        f = split.files[file_no]
        local: Path | None = None
        try:
            local = fetch(f, tmpdir)
            if on_file:
                on_file(f, local.stat().st_size)
            budget = None if quota is None else quota - taken
            reader = (_read_parquet(local, split, f, file_no, plan, budget) if f.fmt == "parquet"
                      else _read_tabular(local, f, file_no, budget))
            for chunk in reader:
                taken += chunk.batch.num_rows
                yield chunk
        except GeneratorExit:
            raise
        except Exception as exc:  # noqa: BLE001  corrupt or unreadable file: report, carry on
            on_error(f, exc)
        finally:
            if local is not None:
                try:
                    local.unlink(missing_ok=True)
                except OSError:
                    pass
