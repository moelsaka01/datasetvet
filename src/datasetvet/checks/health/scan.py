"""Scan planner and streaming reader: full scan or deterministic sample (PLAN.md 5.5). Task 2.8.

- Total bytes <= max_scan_bytes (default 5 GB), or --full: **Full scan**, every row of every
  split, files read in path order.
- Above the limit: **deterministic sample** of up to `sample_rows` rows. Each split gets a
  quota proportional to its rows (bytes when rows are unknown). Within a split, files are
  visited in an order shuffled with the seed until the quota is met. Inside each file read,
  the rows come from **many small chunks spread across the whole file** (Phase 3 change; it was
  whole Parquet row groups): the file is cut into slots of `chunk_rows(quota)` rows (at most
  100, and about 100 or more chunks per split quota) and slots are drawn with the seed, so a
  file sorted by label still gives rows from every part of it. CSV/JSON Lines files are
  counted first, then sampled the same way.
- Files are downloaded one at a time to a temp dir and deleted after reading, so disk use is
  bounded by the largest file. Under sampling, not every file is read.
"""

from __future__ import annotations

import gzip
import json
import math
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
MAX_CHUNK_ROWS = 100  # a sampled file is read in chunks of at most this many rows
MIN_CHUNKS = 100  # ... and in about this many chunks or more when the quota allows


def chunk_rows(quota: int) -> int:
    """Rows per sample chunk for a split quota: at most 100, small enough for ~100 chunks."""
    return max(1, min(MAX_CHUNK_ROWS, quota // MIN_CHUNKS))


def choose_chunks(n_rows: int, want: int, key: str, size: int) -> list[tuple[int, int]]:
    """Seeded (start, length) row ranges in a file of `n_rows`, `want` rows in total, in file
    order. The file is cut into slots of `size` rows; slots are drawn without replacement and
    the last one drawn is cut so the total is exactly `want`."""
    if want >= n_rows:
        return [(0, n_rows)] if n_rows else []
    slots = list(range(math.ceil(n_rows / size)))
    random.Random(key).shuffle(slots)
    picked: list[tuple[int, int]] = []
    total = 0
    for slot in slots:
        if total >= want:
            break
        start = slot * size
        length = min(size, n_rows - start, want - total)
        picked.append((start, length))
        total += length
    return sorted(picked)


@dataclass
class ScanPlan:
    mode: str  # "full" or "sampled"
    seed: int
    bytes_total: int | None
    rows_total: int | None
    sample_rows: int | None = None
    quotas: dict[str, int | None] = field(default_factory=dict)  # split key -> row quota
    reason: str | None = None

    def chunk_rows(self, split_key: str) -> int | None:
        q = self.quotas.get(split_key)
        return chunk_rows(q) if (self.mode == "sampled" and q) else None

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
              "rows are read in small chunks spread across each file read; use --full to "
              "scan everything")
    return ScanPlan("sampled", seed, bytes_total, rows_total, sample_rows=sample_rows,
                    quotas=quotas, reason=reason)


def file_order(split: SplitSource, plan: ScanPlan) -> list[int]:
    idx = list(range(len(split.files)))
    if plan.mode == "sampled":
        random.Random(f"{plan.seed}:{split.key}:files").shuffle(idx)
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


def _rows_key(plan: ScanPlan, split: SplitSource, f: SplitFile) -> str:
    return f"{plan.seed}:{split.key}:{f.path}:rows"


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
    wanted: list[tuple[int, int]] | None = None
    if budget is not None and budget < md.num_rows:
        size = plan.chunk_rows(split.key) or chunk_rows(budget)
        wanted = choose_chunks(md.num_rows, budget, _rows_key(plan, split, f), size)
    for g in range(md.num_row_groups):
        g0 = starts[g]
        rg = md.row_group(g)
        g1 = g0 + rg.num_rows
        if wanted is not None and not any(a < g1 and a + n > g0 for a, n in wanted):
            continue  # no chosen chunk in this row group: not decoded
        avg = rg.total_byte_size / rg.num_rows if rg.num_rows else 0
        # keep each batch near 64 MB in memory, even for image or audio rows
        bsize = int(max(16, min(BATCH_ROWS, (64 << 20) / avg))) if avg else BATCH_ROWS
        offset = g0
        for batch in pf.iter_batches(batch_size=bsize, row_groups=[g]):
            if wanted is None:
                yield Chunk(batch, file_no, f.path, offset, feats)
            else:
                yield from _slices(batch, offset, wanted, file_no, f.path, feats)
            offset += batch.num_rows


def _slices(batch: pa.RecordBatch, offset: int, wanted: list[tuple[int, int]], file_no: int,
            path: str, feats: dict | None) -> Iterator[Chunk]:
    """The parts of `batch` (file rows offset .. offset+len) inside the wanted ranges."""
    end = offset + batch.num_rows
    for a, n in wanted:
        lo, hi = max(a, offset), min(a + n, end)
        if lo < hi:
            yield Chunk(batch.slice(lo - offset, hi - lo), file_no, path, lo, feats)


def _open_text(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rb")
    return open(path, "rb")


def _tabular_batches(path: Path, f: SplitFile) -> Iterator[pa.RecordBatch]:
    fmt = f.fmt
    if fmt in ("csv", "tsv"):
        opts = pacsv.ParseOptions(delimiter="\t" if fmt == "tsv" else ",")
        fh = _open_text(path)
        try:
            reader = pacsv.open_csv(fh, parse_options=opts,
                                    read_options=pacsv.ReadOptions(block_size=1 << 22))
            yield from reader
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
            yield from pa.Table.from_pylist(rows).to_batches(BATCH_ROWS)
        else:
            with _open_text(path) as fh:
                table = pajson.read_json(fh, read_options=pajson.ReadOptions(block_size=1 << 22))
            yield from table.to_batches(BATCH_ROWS)
        return
    raise ValueError(f"unsupported format {fmt!r}")


def _read_tabular(path: Path, split: SplitSource, f: SplitFile, file_no: int, plan: ScanPlan,
                  budget: int | None) -> Iterator[Chunk]:
    wanted: list[tuple[int, int]] | None = None
    if budget is not None:
        n_rows = sum(b.num_rows for b in _tabular_batches(path, f))  # first pass: count
        if budget < n_rows:
            size = plan.chunk_rows(split.key) or chunk_rows(budget)
            wanted = choose_chunks(n_rows, budget, _rows_key(plan, split, f), size)
    offset = 0
    for batch in _tabular_batches(path, f):
        if wanted is None:
            yield Chunk(batch, file_no, f.path, offset, None)
        else:
            yield from _slices(batch, offset, wanted, file_no, f.path, None)
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
                      else _read_tabular(local, split, f, file_no, plan, budget))
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
