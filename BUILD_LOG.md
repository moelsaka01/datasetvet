# Build log

One entry per phase: the model and effort used, what was decided and why, what was measured, and what is still open. Newest last.

| phase | model | effort | status |
|---|---|---|---|
| 1 Planning | Opus 5.5 | high | done 2026-11-19 |
| 2 Core checks (no licences) | Sonnet 5.5 | medium | not started |
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
| Name | `datasetdoctor` kept as the working name | free on PyPI/npm but crowded on GitHub; rename is the owner's call (PLAN.md §1) |

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
