# Build log

One entry per phase: the model and effort used, what was decided and why, what was measured, and what is still open. Newest last.

| phase | model | effort | status |
|---|---|---|---|
| 1 Planning | Opus 5.5 | high | done 2026-11-19 |
| 2 Core checks (no licences) | Sonnet 5.5 planned; run on Opus 5.5 | medium planned | done 2026-11-19 |
| 3 Licence + provenance | Opus 5.5 | high | not started |
| 4 Accuracy eval + launch scan | Opus 5.5 | high | not started |
| 5 Polish, Action, README, launch | Sonnet 5.5 | medium | not started |

---

## Phase 1: planning (2026-11-19, Opus 5.5, high effort)

Run in one Claude Code session (desktop app) on the owner's Windows 11 laptop, Python 3.12.10, on a Claude Pro plan. No paid APIs, no tokens used: every probe was anonymous.

### Decisions

| decision | choice | why |
|---|---|---|
| Language | Python ≥ 3.11 | `huggingface_hub` (built-in 429 handling), ScanCode is a Python library, `pyarrow`/`duckdb` Windows wheels; `pyarrow` 26 needs 3.11 |
| Licence scanner | ScanCode toolkit, as the optional `[scan]` extra | only option that detects licence *notices inside READMEs and web pages*, not just LICENSE files; deterministic, gives scores and lines. askalono: full texts only, last release 2024-10. licensee: needs Ruby |
| Licence statuses | consistent / inconsistent / missing / unknown only | design rule 1 |
| Licence properties | SPDX flags + Creative Commons BY/SA/NC/ND elements only | SPDX data does not publish NC/SA for non-CC licences; showing nothing beats interpreting |
| Full-scan limit | 5 GB of Parquet, then a deterministic row-group sample of up to 1M rows | 5 GB is ~7 min of download at 100 Mbit/s; above it a default run could take hours |
| Row identity | canonical encoding + xxh3_128, two hashes (`row`, `input` without labels) | exact duplicates, plus "same input, different label" leakage |
| Duplicate counting | DuckDB on disk | stays within laptop RAM for large datasets |
| Answer key | DPI `data_summaries` (GitHub, Apache-2.0), not their HF datasets | the HF datasets are filtered training data without licence tags; the GitHub JSON has expert licences + what the card said at audit time |
| Badge | local SVG, factual text, no green | green reads as "safe" |
| Project licence | MIT | matches the owner's other projects (tierview, honest-ml, honest-tests are MIT) |
| Name | **`datasetvet`** (renamed from the working name `datasetdoctor` by the owner after Phase 1) | `datasetdoctor` was free on PyPI/npm but crowded on GitHub (8 repos, `dataset-doctor` taken on PyPI); `datasetvet` is free on PyPI, npm and GitHub (re-checked 2026-11-19) |

### Measured

- **Names:** `datasetdoctor` free on PyPI and npm, 8 GitHub repos use it; `dataset-doctor` taken on PyPI. Free everywhere with 0 GitHub repos: `datasetvet`, `cardvet`, `datapreflight`, `trainvet`.
- **HF rate limits** from live headers: API `q=500;w=300`, resolvers `q=3000;w=300` (anonymous). Docs: free account 1,000 / 5,000 per 5 min. The Dataset Viewer sent no rate-limit headers.
- **HF endpoints** confirmed working: dataset list with cursor pagination, dataset info (`cardData`, `siblings`, `sha`), `/parquet` (Hub and Dataset Viewer), `/size`, `/is-valid`, raw README via `resolve`.
- **Scale:** `HuggingFaceFW/fineweb-edu` has 2,410 Parquet files, 4,523 GB.
- **DPI key:** 109 files, 3,718 entries, 3,490 HF-linked, 804 unique HF repos, 3,342 with a named verifier, 3,133 with the audit-time HF YAML licence.
- **ScanCode on Windows:**
  - failed to install under a long path (MAX_PATH);
  - at a short path it installed in 116 s, to a 637 MB venv;
  - it then crashed on import with `pluggy` 1.7.0, and segfaulted under Git Bash (Git's libmagic);
  - with `pluggy<1.6` + `typecode-libmagic`, run from PowerShell, it detected CC-BY-NC-4.0 / MIT / CC-BY-SA-4.0 correctly on 3 samples, with 3.6–5.7 s index load and <0.1 s per file;
  - the test venvs were deleted afterwards.

### Corrections to the brief

- `Commercially-Verified-Licenses` is a DPI **dataset** (filtered training data), not a checking tool.
- No licence-compliance tool named Calibra was found. The Calibra that exists is robot-dataset observability.
- "Licence properties via SPDX data" is narrower than hoped: SPDX publishes OSI/FSF/deprecated flags, not non-commercial or share-alike. See PLAN.md §5.2.

### Not done / open

- No GitHub repo created, nothing pushed.
- SPDX licence-list data's own licence not verified (GitHub reports NOASSERTION); task 3.3.
- Dataset Viewer rate limits unknown; measured in Phase 4.
- Launch-scan bandwidth unknown until task 4.1 sums the top-500 sizes.

---

## Phase 2: core checks without licences (2026-11-19)

**Model:** planned Sonnet 5.5 at medium effort. This session actually ran on **Opus 5.5**, so the log records that rather than the planned model.

**Setup:** run in one Claude Code session (desktop app), Windows 11, Python 3.12.10. The folder had been renamed `datasetdoctor` → `datasetvet` and the old `.venv` deleted, so the venv was recreated (`py -3.12 -m venv .venv`, `pip install -e ".[dev]"`).

**Tokens:** no HF token was present (no `HF_TOKEN`, no login file), so every live call was anonymous. The code reads a token only through `huggingface_hub.get_token()`, sends it only to `huggingface.co` / `datasets-server.huggingface.co` (on every redirect hop), and never logs, caches or reports it. Reports show only `authenticated: yes/no`. Only free endpoints were used.

### Licence scanner: default vs extra (checked before coding)

- The plan had **no default licence-text scanner**. ScanCode is the optional `[scan]` extra (652 MB venv).
- With the core install, licence evidence is only:
  - the card's YAML `license`;
  - GitHub's detected licence, when `GITHUB_TOKEN` is set.
- Every text-based claim is `unknown (scanner not installed)`. PLAN §4 now says this explicitly.
- §8 did not say which configuration the accuracy evaluation runs. It now runs `default` and `scancode` separately, on the same key, split and frozen config, with one confusion matrix and set of metrics each, never pooled. Tasks 4.5/4.6 are updated to match.
- Open for the owner: whether the core install should get a small built-in matcher (PLAN §12).

### Built (tasks 2.1–2.13)

| task | files | state |
|---|---|---|
| 2.1 models, closed status enums, JSON round-trip | `model.py` | done; a status outside its family's enum raises |
| 2.2 HTTP layer | `http.py` | done. RateLimit/RateLimit-Policy limiter paces a bucket below 20% of q; 429 sleeps `Retry-After` or `t` (3 retries); 5xx/connection retries with backoff; on-disk cache for revision-pinned GETs; manual redirects; UA has no personal data |
| 2.3 adapter protocol + registry | `hubs/base.py` | done; interface changes listed in PLAN §6 |
| 2.4 HF adapter | `hubs/huggingface.py`, `tests/fixtures/hf/` | done; recorded fixtures for imdb, gated `cais/hle`, viewer-disabled `nvidia/simready-assets` (front matter only, no card prose); `record.py` re-records them; one `network` test |
| 2.5 card check | `checks/card.py` | done except HF-id/SPDX validity (task 3.1) |
| 2.6 link check | `checks/links.py` | done; status table reproduced against a local server |
| 2.7 row hashing | `checks/health/rowhash.py` | done |
| 2.8 scan planner + reader | `checks/health/scan.py` | done; sampling detail in PLAN §5.5 |
| 2.9 duplicates + leakage | `checks/health/duplicates.py` | done; DuckDB on disk |
| 2.10 empty, corrupt, labels | `empty.py`, `labels.py`, `runner.py` | done |
| 2.11 PII patterns | `checks/health/pii.py` | done; masked examples |
| 2.12 JSON + terminal, CLI `check` | `report/`, `cli.py`, `pipeline.py`, `config.py` | done |
| 2.13 CI | `.github/workflows/ci.yml` | **written, not run.** Nothing is pushed. The matrix covers Windows and Ubuntu on 3.11–3.13, but only 3.12 on Windows was run locally |

**Checks:**
- `pytest`: 125 offline tests pass in about 28 s, plus 1 live test with `-m network`.
- `ruff check src tests`: clean.
- `mypy src`: clean.

### Live runs (anonymous, 2026-11-19)

| dataset | why | result | data scan |
|---|---|---|---|
| `stanfordnlp/imdb` | plan's target; 3 splits, ClassLabel | duplicates found (test 199, train 96, unsupervised 493 extra copies); test∩train 123 shared inputs, 0 with different labels; 89 text values match the email pattern; 2 links ok | **Full scan**, 100,000 rows, 83.4 MB, 14.0 s scan (23 s wall without cache) |
| `stanfordnlp/imdb` `--max-scan-bytes 30MB --sample-rows 20000 --seed 1` | sampled path | header `Sampled: 20,000 of 100,000 rows (seed 1)`; counts labelled "at least"; same sample on re-run | 8.6 s; still 83.4 MB downloaded (one file per split) |
| `cornell-movie-review-data/rotten_tomatoes` | small, clean | card `license: unknown` → licence field `missing`; no duplicates, no leakage, no PII matches; 3 links ok | **Full scan**, 10,662 rows, 0.9 MB, 3.2 s |
| `dair-ai/emotion` | 2 configs | `split/train` 1 duplicate, `unsplit/train` 686; leakage test∩train 11, test∩val 3, train∩val 5, each with different labels | **Full scan**, 436,809 rows, 28.2 MB, 20.8 s |
| `cais/hle` | gated (auto) | card readable anonymously; data `not checked` (gated, terms never accepted); 3 stated links ok | not checked |
| `nvidia/simready-assets` | Dataset Viewer disabled | data `not checked`: viewer disabled and no `configs`, so nothing states which files are data | not checked |
| `nobody-xyz/does-not-exist-123` | error path | exit 1, "not found on the Hugging Face Hub, or private …" | – |

**Throughput on this laptop:**
- About 7,000 rows/s (6 MB/s) for IMDB's long reviews, and about 21,000 rows/s for emotion's short tweets, including download.
- The streaming pass is CPU-bound in Python (canonical encoding + xxh3 per row). At these rates a 5 GB full scan of short-text data would take tens of minutes, not the ~7 minutes of download estimated in PLAN §5.5.
- 14–19 HTTP requests per dataset.

### Problems found and fixed during the build

1. The DuckDB examples and leakage queries built per-group lists, which cannot spill. They hit Out-Of-Memory under a memory cap. Both now use only aggregates, joins and windows; tested at 64 MB with 1.1 M rows (32 MB is below DuckDB's floor for these joins).
2. The no-conversion fallback treated `nvidia/simready-assets`' `.metadata/*.json` package files as data. Now hidden paths are never data, and a viewer-disabled repo without `configs` is `not checked`.
3. `cais/hle`'s `## ✏️ Citation` heading and its `[Website] | [Paper] | [GitHub]` links were missed. Both rules are clarified in PLAN §5.1 and covered by tests.
4. IMDB's unlabelled split (`-1`) showed up as "different labels" and "absent from train". `-1` is now treated as "no label" for ClassLabel columns.
5. Sampled label shares are biased on files sorted by label (row groups are clusters). The report now says so under sampling.

### Not done / open

- CI (2.13) not run; nothing pushed. Python 3.11 and 3.13 not tested locally (only 3.12 is installed).
- HF-id/SPDX validity, licence consistency and provenance: Phase 3. Reports list them under "Not checked".
- `config.py` reads flags and `DATASETVET_*` environment variables; a config file is not supported yet.
- The footer phrase "you may" conflicts with the Phase 5 banned-words list (PLAN §12).
- Peak memory was not measured (no `time`/`psutil` on this machine).
- Throughput suggests the 5 GB full-scan default may be slow for short-row datasets; worth re-measuring in task 4.1 before fixing the launch-scan limits.
