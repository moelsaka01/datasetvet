"""Within-split duplicates and cross-split leakage on DuckDB, on disk (PLAN.md 5.5). Task 2.9.

Hashes go into an on-disk DuckDB table (split, config, file_no, row, row_h, input_h) with a
memory limit and a spill directory, so the queries work when the hash table exceeds RAM.

- Duplicates: rows sharing a `row` hash inside one split; the count is the number of extra
  copies (a row seen 3 times counts 2).
- Leakage: `input` hashes present in two splits of the same config. Per pair: distinct shared
  inputs, rows involved on each side, % of the smaller split, and how many shared inputs carry
  different labels in the two splits (their sets of full-row hashes differ).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

EXAMPLES = 5


@dataclass
class DupResult:
    split: str
    rows: int
    extra_copies: int
    examples: list[list[list[int]]] = field(default_factory=list)  # groups of [file, row]


@dataclass
class LeakResult:
    config: str
    split_a: str
    split_b: str
    rows_a_total: int
    rows_b_total: int
    shared_inputs: int
    rows_a: int
    rows_b: int
    label_differs: int
    examples: list[dict[str, Any]] = field(default_factory=list)

    @property
    def pct_of_smaller(self) -> float:
        if self.rows_a_total <= self.rows_b_total:
            n, total = self.rows_a, self.rows_a_total
        else:
            n, total = self.rows_b, self.rows_b_total
        return 100.0 * n / total if total else 0.0

    @property
    def smaller(self) -> str:
        return self.split_a if self.rows_a_total <= self.rows_b_total else self.split_b


_SCHEMA = pa.schema([
    ("split", pa.string()), ("config", pa.string()), ("file_no", pa.int32()),
    ("row", pa.int64()), ("row_h", pa.binary(16)), ("input_h", pa.binary(16)),
])


class HashStore:
    def __init__(self, workdir: Path, memory_limit: str = "1GB"):
        self.path = Path(workdir) / "hashes.duckdb"
        spill = Path(workdir) / "duckdb-spill"
        spill.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(self.path))
        self.con.execute(f"SET memory_limit='{memory_limit}'")
        self.con.execute(f"SET temp_directory='{spill.as_posix()}'")
        self.con.execute("SET preserve_insertion_order=false")
        self.con.execute("SET threads=2")
        self.con.execute(
            "CREATE TABLE h (split VARCHAR, config VARCHAR, file_no INTEGER, row BIGINT, "
            "row_h BLOB, input_h BLOB)")

    def add(self, split: str, config: str, file_no: int, first_row: int,
            row_h: list[bytes], input_h: list[bytes]) -> None:
        n = len(row_h)
        if not n:
            return
        tbl = pa.table({
            "split": pa.array([split] * n, pa.string()),
            "config": pa.array([config] * n, pa.string()),
            "file_no": pa.array([file_no] * n, pa.int32()),
            "row": pa.array(range(first_row, first_row + n), pa.int64()),
            "row_h": pa.array(row_h, pa.binary(16)),
            "input_h": pa.array(input_h, pa.binary(16)),
        }, schema=_SCHEMA)
        self.con.register("incoming", tbl)
        self.con.execute("INSERT INTO h SELECT split, config, file_no, row, row_h::BLOB, "
                         "input_h::BLOB FROM incoming")
        self.con.unregister("incoming")

    def duplicates(self) -> list[DupResult]:
        totals = self.con.execute(
            "SELECT split, count(*), count(*) - count(DISTINCT row_h) FROM h GROUP BY split "
            "ORDER BY split").fetchall()
        # Only spillable operators (hash aggregates, joins, windows): no per-group lists.
        ex = self.con.execute(f"""
            WITH g AS (
              SELECT split, row_h, min(file_no) f0, min(row) r0
              FROM h GROUP BY split, row_h HAVING count(*) > 1),
            top AS (
              SELECT split, row_h, f0, r0 FROM g
              QUALIFY row_number() OVER (PARTITION BY split ORDER BY f0, r0, row_h)
                      <= {EXAMPLES})
            SELECT h.split, h.row_h, h.file_no, h.row
            FROM h JOIN top ON h.split = top.split AND h.row_h = top.row_h
            ORDER BY top.split, top.f0, top.r0, top.row_h, h.file_no, h.row""").fetchall()
        examples: dict[str, list[list[list[int]]]] = {}
        last: tuple[str, bytes] | None = None
        for split, row_h, f, r in ex:
            groups = examples.setdefault(split, [])
            if (split, row_h) != last:
                groups.append([])
                last = (split, row_h)
            if len(groups[-1]) < EXAMPLES:
                groups[-1].append([f, r])
        return [DupResult(s, n, extra, examples.get(s, [])) for s, n, extra in totals]

    def split_rows(self) -> dict[str, int]:
        return dict(self.con.execute("SELECT split, count(*) FROM h GROUP BY split").fetchall())

    def leakage(self) -> list[LeakResult]:
        totals = self.split_rows()
        # Labels differ for a shared input when its sets of full-row hashes differ between the
        # two splits: equal sets <=> |A| = |B| = |A n B|. Counts only, so DuckDB can spill.
        pairs = self.con.execute("""
            WITH d AS (
              SELECT config, split, input_h, count(*) n, count(DISTINCT row_h) k
              FROM h GROUP BY config, split, input_h),
            p AS (
              SELECT a.config, a.split sa, b.split sb, a.input_h, a.n na, b.n nb,
                     a.k ka, b.k kb
              FROM d a JOIN d b
                ON a.config = b.config AND a.input_h = b.input_h AND a.split < b.split),
            s AS (SELECT DISTINCT config, split, input_h, row_h FROM h),
            c AS (
              SELECT x.config, x.split sa, y.split sb, x.input_h, count(*) common
              FROM s x JOIN s y
                ON x.config = y.config AND x.input_h = y.input_h AND x.row_h = y.row_h
               AND x.split < y.split
              GROUP BY x.config, x.split, y.split, x.input_h)
            SELECT p.config, p.sa, p.sb, count(*), sum(p.na), sum(p.nb),
                   count(*) FILTER (WHERE NOT (p.ka = p.kb AND p.ka = coalesce(c.common, 0)))
            FROM p LEFT JOIN c
              ON p.config = c.config AND p.sa = c.sa AND p.sb = c.sb AND p.input_h = c.input_h
            GROUP BY p.config, p.sa, p.sb
            ORDER BY p.config, p.sa, p.sb""").fetchall()
        # every same-config split pair is reported, including the ones with no overlap
        configs: dict[str, list[str]] = {}
        for cfg, split in self.con.execute(
                "SELECT DISTINCT config, split FROM h ORDER BY config, split").fetchall():
            configs.setdefault(cfg, []).append(split)
        found = {(c, a, b): (n, ra, rb, d) for c, a, b, n, ra, rb, d in pairs}
        out = []
        for cfg, splits in configs.items():
            for i, a in enumerate(splits):
                for b in splits[i + 1:]:
                    n, ra, rb, d = found.get((cfg, a, b), (0, 0, 0, 0))
                    res = LeakResult(cfg, a, b, totals.get(a, 0), totals.get(b, 0),
                                     int(n), int(ra or 0), int(rb or 0), int(d))
                    if n:
                        res.examples = self._leak_examples(a, b)
                    out.append(res)
        return out

    def _leak_examples(self, a: str, b: str) -> list[dict[str, Any]]:
        rows = self.con.execute(f"""
            WITH x AS (SELECT input_h, min(file_no) f, arg_min(row, file_no * 1e12 + row) r
                       FROM h WHERE split = ? GROUP BY input_h),
                 y AS (SELECT input_h, min(file_no) f, arg_min(row, file_no * 1e12 + row) r
                       FROM h WHERE split = ? GROUP BY input_h)
            SELECT x.f, x.r, y.f, y.r FROM x JOIN y USING (input_h)
            ORDER BY x.f, x.r LIMIT {EXAMPLES}""", [a, b]).fetchall()
        return [{"a": [fa, ra], "b": [fb, rb]} for fa, ra, fb, rb in rows]

    def close(self) -> None:
        self.con.close()
