# datasetdoctor: plan

> **Before you train on it, check it.**
> A CLI that checks a dataset and writes a report card of verifiable facts: what the card says, what the licence files and the source say, whether the links work, and what is in the data (duplicates, cross-split leakage, empty rows, label balance, PII-pattern matches). It never says a dataset is "safe to use", and it is not legal advice.

Status: **Phase 1 (planning) complete, 2026-11-19.** Nothing below is implemented yet. Every "measured" figure in this file was measured on 2026-11-19 from this laptop (Windows 11, Python 3.12.10) and is listed with how it was measured in [Feasibility evidence](#9-feasibility-evidence-measured-2026-11-19).

Contents: [1 Name](#1-name) · [2 Competitors](#2-competitors) · [3 Architecture](#3-architecture) · [4 Licence scanner](#4-licence-scanner-choice) · [5 Checks](#5-checks-exact-rules-and-statuses) · [6 Hub adapters](#6-hub-adapter-interface) · [7 Reports and badge](#7-report-formats-and-badge) · [8 Accuracy evaluation](#8-accuracy-evaluation) · [9 Feasibility evidence](#9-feasibility-evidence-measured-2026-11-19) · [10 Launch scan](#10-launch-scan-top-500-hf-datasets) · [11 Task list](#11-phased-task-list) · [12 Risks and open questions](#12-risks-and-open-questions)

---

## 1. Name

| name | PyPI | npm | GitHub repos with the name |
|---|---|---|---|
| `datasetdoctor` | free | free | 8, incl. `pixerwar/datasetdoctor` ("health check for your fine-tuning datasets", 1 star, created 2026-06-30) |
| `dataset-doctor` | **taken** | free | 87, many of them dataset-quality CLIs |
| `datasetvet` | free | free | 0 |
| `cardvet` | free | free | 0 |
| `datapreflight` | free | free | 0 |
| `trainvet` | free | free | 0 |

(PyPI/npm: HTTP 404 from the registry JSON endpoints; GitHub: repository search `in:name`.)

**Verdict:** `datasetdoctor` is technically free on all three registries, but it is crowded: `pip install dataset-doctor` (with a hyphen) installs someone else's package, and an unrelated `datasetdoctor` repo already does fine-tuning dataset health checks. Three alternatives that are free everywhere and have no GitHub repos:

1. **`datasetvet`**: "vet" means both check carefully and the doctor pun. Recommended.
2. **`datapreflight`**: the "check before you take off" metaphor fits "before you train on it".
3. **`cardvet`**: short, but undersells the data-health half.

The scaffold uses `datasetdoctor`. The package name appears in `pyproject.toml`, `src/datasetdoctor/` and the docs only, so a rename now is cheap. **Decision for the owner.**

## 2. Competitors

| tool | what it does | licence consistency vs source | provenance (parent licence) | link checks | data health (dups, leakage, PII) | arbitrary HF dataset |
|---|---|---|---|---|---|---|
| Data Provenance Explorer / Collection (DPI) | Hand-audited licences for ~1,858 fine-tuning datasets (paper) / 3,718 entries (repo today); filter and download | audited by humans, not a checker | yes, for its catalogue | no | no | **no**, fixed catalogue |
| `DataProvenanceInitiative/Commercially-Verified-Licenses` | A **dataset** (a filtered subset of DPI's collection), not a tool | n/a | n/a | n/a | n/a | n/a |
| Calibra | Robot-dataset observability (HF forum, 2025); quality, not licensing | no | no | no | partial (robotics) | robotics datasets |
| Dingo (MigoXLab/DataEval, Apache-2.0, 771 stars) | Rule + **LLM** data-quality evaluation of samples | no | no | no | yes, quality rules; LLM optional | yes |
| HF card validation (`huggingface_hub` `DatasetCard.validate`, Hub YAML checks) | Validates YAML metadata, including the licence id being on HF's list | no | no | no | no | yes |
| LicenseRec / "license drift" (arXiv 2509.09873) and "Permissive-washing" audit (arXiv 2602.08816) | Research audits + prototype rule engines that recommend compatible licences | partial | partial | no | no | research pipelines; **LicenseRec makes compatibility judgements** |

**How we differ (5 lines):**
1. Nothing found combines licence consistency, provenance, links and data health for an arbitrary dataset in one report; each tool above covers at most one or two of those.
2. We check the card against the *source's own* licence and the *parent dataset's* licence, with an evidence link pinned to a commit for every fact.
3. We report facts and four licence statuses only; LicenseRec and similar engines give compatibility verdicts, and we deliberately do not.
4. No AI in any decision (Dingo and LicenseGPT-style tools use models); every result is reproducible from the same inputs.
5. Full-data scans by default, with cross-split leakage as a first-class result and the scan type (full or sampled) printed on every report.

Limits of this check: web searches plus the repos and papers above; a tool released very recently or under a different name could exist. Re-check before launch (task 5.8).

## 3. Architecture

### Language: Python 3.11+

- `huggingface_hub` (Apache-2.0) is the Hub's official client and, from 1.2.0, retries 429s by reading the `RateLimit` header ([HF docs](https://huggingface.co/docs/hub/rate-limits)).
- ScanCode toolkit (the recommended scanner, §4) is a Python library: import it, no subprocess, no second runtime.
- `pyarrow` and `duckdb` ship Windows wheels and read Parquet in batches; `license-expression` (Apache-2.0, from the ScanCode authors) parses and compares SPDX expressions.
- Python 3.11 minimum because `pyarrow` 26 requires it; the owner's laptop has 3.12.10.

### Pipeline

```text
 dataset ref ("hf:stanfordnlp/imdb", or a URL)
   |
   v
 hub registry -> adapter (v1: Hugging Face)        pin revision (commit sha) first
   |
   +-- card + file list + stated sources + parents   (never sampled)
   |      |
   |      +-> card check -> licence consistency -> provenance -> links
   |
   +-- data splits (converted Parquet or original files)
          |
          +-> scan planner: full scan if bytes <= limit, else deterministic sample
          +-> one streaming pass: row hashes, empty rows, label counts, PII matches
          +-> duplicate / leakage queries over the hash table (DuckDB, on disk)
   |
   v
 Report (JSON, the single source of truth) -> terminal / Markdown / HTML / badge SVG
```

Every check is a pure function of fetched inputs plus fixed tables; every network fetch goes through one HTTP layer that pins revisions, caches responses on disk and obeys rate limits. Tests run fully offline against recorded fixtures.

### Module layout

```text
src/datasetdoctor/
  cli.py                 argparse entry point: `datasetdoctor check <ref>`, `datasetdoctor badge`
  config.py              limits (scan bytes, sample size, timeouts), loaded from flags/env/file
  model.py               dataclasses: DatasetRef, Evidence, Fact, CheckResult, Report; status enums
  http.py                one session: RateLimit-header limiter, retries, on-disk cache, user agent
  hubs/
    base.py              HubAdapter protocol, SourceResolver protocol, registry
    huggingface.py       v1 adapter
    github.py            v1: source resolver (licence of a GitHub repo); v2: dataset adapter
    web.py               plain-URL source resolver (link status only + licence text if a licence page)
  licences/
    spdx.py              license-expression wrapper; parse, normalise, compare
    hf_ids.py            HF licence id -> SPDX id / family / non-SPDX table (data/hf_licence_ids.csv)
    scanner.py           ScanCode wrapper (optional extra); returns detections with scores and lines
    properties.py        published licence properties: SPDX flags + Creative Commons elements
  checks/
    card.py  licence.py  provenance.py  links.py
    health/
      scan.py            scan planner + streaming reader (full vs sampled)
      rowhash.py         canonical row encoding + 128-bit hash
      duplicates.py      within-split duplicates and cross-split leakage
      empty.py  labels.py  pii.py
  report/
    json_out.py  terminal.py  markdown.py  html.py  badge.py
  data/                  hand-checked tables (CSV) with a source URL per row
eval/                    DPI answer-key builder, runner, metrics (Phase 4)
launch/                  resumable top-500 scan (Phase 4)
tests/                   offline unit tests + recorded HTTP fixtures; `-m network` for live tests
docs/                    CHECKS.md (rules), REPORT_SCHEMA.md, EVAL.md
```

### Dependencies (all free, permissive licences)

| package | why | licence |
|---|---|---|
| `huggingface_hub` | Hub API, rate-limit-aware downloads, token from the user's own login | Apache-2.0 |
| `pyarrow` | Parquet batches | Apache-2.0 |
| `duckdb` | on-disk hash table and duplicate/leakage queries beyond RAM | MIT |
| `xxhash` | 128-bit row hashes (xxh3_128) | BSD-2-Clause |
| `license-expression` | SPDX parse/normalise/equivalence | Apache-2.0 |
| `pyyaml` | card front matter | MIT |
| `phonenumbers` | phone-number validation after regex candidates | Apache-2.0 |
| `rich` | terminal report | MIT |
| extra `[scan]`: `scancode-toolkit-mini` | licence text detection (§4) | Apache-2.0 AND CC-BY-4.0 (data) |

Tokens: an HF token or a GitHub token is read only from the user's own environment (`HF_TOKEN`, `huggingface-cli login` storage, `GITHUB_TOKEN`). The tool never asks for, prints, logs or stores a token, and reports show only "authenticated: yes/no".

## 4. Licence scanner choice

| scanner | accuracy on our inputs | Windows | install weight | licence | maintained |
|---|---|---|---|---|---|
| **ScanCode toolkit** (`scancode-toolkit-mini` 32.5.0) | Detects full licence texts **and** notices/references inside prose ("released under CC BY-NC 4.0", "## License\nMIT") using ~2,300 curated licences and tens of thousands of rules; returns SPDX expressions, match scores and line numbers | works on this laptop after 3 measured fixes (§9): short venv path (MAX_PATH), `pluggy<1.6`, `typecode-libmagic` | 120 MB wheel; **652 MB venv** | Apache-2.0 (code), CC-BY-4.0 (licence data) | release 2026-01-15, pushed 2026-11-11, 2,676 stars |
| askalono (Rust CLI) | Full licence texts only (Dice similarity over normalised text); not designed for notices inside READMEs | Windows binary in releases | single small binary | Apache-2.0 | last release 0.5.0, 2024-10-22; no PyPI package |
| licensee (Ruby; what GitHub's API uses) | LICENSE files and a README "License" section; small licence set (choosealicense.com) | needs a Ruby toolchain | Ruby + gems | MIT | active (pushed 2026-11-16) |
| SPDX licence-list template matching | Exact-ish full-text matching against SPDX templates; strict and slow, no notice detection | any | small | SPDX data (licence: repo reports NOASSERTION; to verify) | active |

**Recommendation: ScanCode toolkit**, installed as an optional extra (`pip install datasetdoctor[scan]`).

- It is the only option that handles our hardest input, licence *statements inside dataset READMEs and web pages*, not just LICENSE files.
- It is deterministic and gives a score and the matched lines, which become the report's evidence.
- Its licence keys and SPDX mappings come from the same project as `license-expression`, so normalisation and comparison use one consistent licence database.

Costs and how we contain them:
- **Weight.** The core install (card check, SPDX validation, links, data health) does not need ScanCode. Without the extra, text-based licence sources report `unknown (scanner not installed)`; the report says so on its first line.
- **Windows install.** The extra pins `pluggy<1.6` and adds `typecode-libmagic` on Windows. The install docs say to enable long paths or create the venv at a short path such as `C:\dd\.venv`, and to run from PowerShell, not Git Bash (Git's libmagic segfaults ScanCode). CI tests the extra on Windows.
- **Cross-check, not a second opinion.** For GitHub sources we also record GitHub's own detected licence (`/repos/{o}/{r}/license`, which is licensee) as a separate, labelled fact. If ScanCode and GitHub disagree, both are shown and the status is `unknown`, never a guess.

## 5. Checks: exact rules and statuses

Every check emits **facts** (each with evidence: URL, commit sha, file path, line range when known, fetch time) and one **status**. No check produces an overall "safe" or a grade.

| check family | allowed statuses |
|---|---|
| licence consistency, provenance | `consistent`, `inconsistent`, `missing`, `unknown` (only these four) |
| card fields | `present`, `missing`, `invalid` |
| links | `ok`, `dead`, `restricted`, `unreachable`, `unknown` |
| data health | `none found`, `found`, `not checked` (+ counts; + `Full scan` or `Sampled: N of M rows`) |

### 5.1 Card check (never sampled)

| field | source | rule | status |
|---|---|---|---|
| licence | card YAML `license` (string or list), plus `license_name` / `license_link` when `license: other` | each value looked up in `data/hf_licence_ids.csv` (HF's published id list) | `present` if every value maps to an SPDX id or a named non-SPDX licence; `invalid` if a value is not an HF id; `missing` if absent, empty or `unknown` |
| licence is SPDX | same | mapping gives an SPDX id (case-insensitive SPDX match, e.g. `cc-by-nc-4.0` -> `CC-BY-NC-4.0`) | fact: "SPDX: CC-BY-NC-4.0" / "family id `bsd`, not a single licence" / "non-SPDX: llama2" / "`other` with license_name X" |
| required metadata | YAML | `pretty_name` or a top-level heading; `language` (if text modality); `task_categories`; `size_categories`; `configs` or `dataset_info` | `present` / `missing` per field |
| citation | README body | a `Citation` heading with a non-empty code block, or a BibTeX entry (`@\w+{`) anywhere, or a DOI / arXiv id in a citation section | `present` / `missing` |
| stated source | YAML `source_datasets`; README "Dataset Description" bullets (Homepage, Repository, Paper, Point of Contact); repo-level links | at least one URL or parent id stated | `present` / `missing`; each URL becomes a link-check target |

HF family ids (`bsd`, `cc`, `gpl`, `lgpl`, `gfdl`, `openrail`) are reported as "a family, not a specific licence": the card check is `present`, but every consistency comparison involving them is `unknown`.

### 5.2 Licence consistency (never sampled)

**Licence claims collected**, each normalised to an SPDX expression (or a ScanCode `LicenseRef-scancode-*` key for non-SPDX licences):

| claim | from | how |
|---|---|---|
| C1 card field | YAML `license` | `hf_ids` table |
| C2 card text | README body (YAML stripped) | ScanCode; keep detections with score >= 90 (threshold frozen in Phase 3 on the dev split) |
| C3 repo licence files | files named `LICEN[CS]E*`, `COPYING*`, `*.license` anywhere in the repo | ScanCode |
| C4 source licence | each stated source: GitHub repo -> its licence file(s) via raw URL + GitHub's detected licence; web page -> ScanCode on the page text only if the page is a licence/terms page by URL path; HF dataset -> its C1 | adapter / resolver |

**Comparison rule** (C1 against each of C2, C3, C4; C2–C4 are not compared with each other, only listed):

| status | rule |
|---|---|
| `consistent` | both sides have a detection and their expressions are equivalent per `license-expression` (`Licensing.is_equivalent`) after normalisation |
| `inconsistent` | both sides have a detection and they are not equivalent. Sub-fact: `differs` or `subset` (one side's licence keys are a strict subset of the other's, e.g. card `MIT`, repo `MIT AND CC-BY-4.0`) |
| `missing` | the source exists and was read, but contains no licence statement (e.g. GitHub repo with no LICENSE and GitHub reports none) |
| `unknown` | anything else: fetch failed, page not text, ScanCode score below threshold, ScanCode and GitHub disagree, family id, `other` without a licence name, multiple conflicting detections in one source, scanner not installed |

The report line always shows both sides verbatim, e.g.
`Card says MIT (README.md@3f2a1c, YAML line 3); source github.com/org/repo LICENSE@9b1e0d says CC-BY-NC-4.0 (score 100, lines 1-12); these differ.`

**Licence properties** (shown next to each licence, never used to decide anything):
- From the SPDX licence list: OSI-approved, FSF-libre, deprecated id.
- For Creative Commons licences only: the licence elements BY / SA / NC / ND, which are part of each licence's published name and deed (creativecommons.org). Kept in `data/cc_elements.csv` with the deed URL per row.
- Nothing else. The SPDX list does **not** publish properties such as "non-commercial" for non-CC licences, so for those the report shows no property rather than an interpretation. (This narrows design rule 1's "properties via SPDX data": SPDX data alone does not carry NC/SA.)

### 5.3 Provenance (never sampled)

- **Parents** are only *declared* derivations: YAML `source_datasets` entries that resolve to a dataset (`extended|<id>`, an HF repo id, or a URL another adapter can resolve). README links to other datasets are listed as "mentioned", never treated as parents.
- For each parent: resolve with the matching adapter (cross-hub allowed), read its C1 (and C3 where cheap), compare with the child's C1 using the §5.2 rule and statuses, and show both licences' properties side by side.
- Depth limit 2 by default (`--provenance-depth`), cycle detection by `(hub, id)`, every parent pinned to a revision.
- Unresolvable parent (`original`, `extended|other-foo`, free text) -> `unknown`, with the raw value shown.

### 5.4 Links (never sampled)

- Targets: every stated source URL, `license_link`, URLs in the card's metadata fields, and repo files referenced from the card (`configs[].data_files` paths that do not exist in the file list -> "missing file").
- Method: `HEAD`, falling back to `GET` with a 64 KB cap; follow up to 5 redirects; timeout 15 s; 2 retries with backoff; one request per host per second; obey `robots.txt` for non-API hosts.

| status | rule |
|---|---|
| `ok` | final response 2xx |
| `dead` | 404 or 410, or DNS NXDOMAIN; missing repo file |
| `restricted` | 401, 403, 451, or an HF gated repo |
| `unreachable` | timeout / connection error after retries, or 5xx after retries |
| `unknown` | 429 that did not clear, or 3xx loops |

The report shows the final URL and status code. A dead link is a fact about today; the report says when it was checked.

### 5.5 Data health (full scan by default)

**Data source per split:** HF's Parquet conversion (`refs/convert/parquet`) when it exists and its `/parquet` response has `partial: false`; otherwise the original files if they are Parquet, CSV or JSON Lines; otherwise `not checked (unsupported format)`.

**Scan planner:** total bytes from the Dataset Viewer `/size` endpoint (or the file list).
- `bytes <= 5 GB` (default `--max-scan-bytes 5GB`): **Full scan**, every row of every split.
- Above the limit: **deterministic sample**: whole Parquet row groups chosen with a fixed seed (recorded in the report), stratified so every split and file contributes in proportion to its rows, up to `--sample-rows 1,000,000`. The report header says `Sampled: N of M rows (seed S)`.
- Files are downloaded one at a time to a temp dir and deleted after reading (one resolver request per file, not many range reads), so disk use is bounded by the largest file.
- 5 GB: a full scan on a laptop is mostly download time (about 7 minutes at 100 Mbit/s; measured throughput is a Phase 2 task). Above it, a default run could take hours, so the user opts in with `--full`.

**Row identity:** canonical encoding of each row: columns in sorted name order, each value type-tagged (null, bool, int, float as IEEE-754 bits, string as UTF-8, bytes, nested lists/structs recursively; images/audio as their raw bytes). Hash: xxh3_128. Two hashes per row:
- `row` (all columns), and
- `input` (all columns except label columns: `ClassLabel` features in `dataset_info`, else columns named `label`/`labels`), so "same text, different label" leakage is caught.
Collision bound stated in the report: about 1.5e-21 for 1e9 rows (birthday bound for 128 bits).

| sub-check | rule | output |
|---|---|---|
| within-split duplicates | rows sharing a `row` hash inside one split | count of extra copies, % of split, up to 5 example row indices |
| cross-split leakage | `input` hashes present in more than one split (e.g. train ∩ test) | count per split pair, % of the smaller split, examples; separately how many of those also differ in label |
| empty rows | every column null or empty string / empty list | count, examples |
| corrupt data | file fails to open or a batch fails to decode | file path + error; the split's other results are marked partial |
| label balance | per label column, per split: counts and shares; labels present in test but not in train | table; no "imbalanced" verdict, just the max/min ratio |
| PII patterns | string columns only: email regex (RFC 5322-lite); phone: regex candidates validated with `phonenumbers` (international `+` format by default; `--phone-region XX` adds national formats) | count of matching values per column; examples shown **masked** (`j***@e***.com`); the report says "pattern matches", not "contains personal data" |

Under sampling, duplicate and leakage counts are lower bounds and are labelled "at least".

## 6. Hub adapter interface

```python
class HubAdapter(Protocol):
    name: str                                    # "huggingface", later "kaggle", "zenodo", "github"
    def matches(self, ref: str) -> bool          # "hf:org/name", "https://huggingface.co/datasets/..."
    def resolve(self, ref: str) -> DatasetRef    # hub, id, revision pinned to a commit sha / version
    def card(self, ds: DatasetRef) -> Card       # raw text, parsed metadata, evidence
    def files(self, ds: DatasetRef) -> list[RepoFile]
    def read_text(self, ds: DatasetRef, path: str, max_bytes: int) -> TextBlob
    def native_licences(self, ds: DatasetRef) -> list[LicenceClaim]   # HF YAML, Zenodo metadata.license, Kaggle licenses[]
    def stated_sources(self, card: Card) -> list[LinkRef]
    def parents(self, card: Card) -> list[ParentRef]                  # may point at another hub
    def splits(self, ds: DatasetRef) -> list[SplitSource]             # name, files, rows, bytes, format, partial flag
    def open_split(self, split: SplitSource, plan: ScanPlan) -> Iterator[pa.RecordBatch]

class SourceResolver(Protocol):                  # things that are sources, not datasets
    def matches(self, url: str) -> bool
    def licence_claims(self, url: str) -> list[LicenceClaim]
    def link_status(self, url: str) -> LinkResult
```

- The registry tries adapters, then resolvers, in order; `ParentRef` carries a URL or `hub:id`, so an HF card can name a Zenodo record or GitHub repo as its parent and the provenance check follows it with the right adapter.
- v1 ships `huggingface` (adapter) plus `github` and `web` (resolvers).
- v2 notes, not verified in Phase 1: Zenodo has an open REST API with `metadata.license`; Kaggle's API needs a free API key (the user's own); a GitHub-hosted dataset adapter reuses the `github` resolver plus a file reader. Each needs its own feasibility check before work starts.

## 7. Report formats and badge

- **JSON** (`--json out.json`) is the single source of truth, with `schema_version`. It holds the tool version, ScanCode version and licence-DB version, the dataset ref and pinned sha, the scan type, the time, every fact with its evidence, and every status. All other formats render from it, so they cannot disagree.
- **Terminal:** one block per section: status word, the facts as one-line sentences, evidence links. The first line is the scan type and anything not checked.
- **Markdown** (`--md`), for PRs and issues, and **HTML** (`--html`): one static file, no JavaScript, no external requests, links to evidence. The HTML is the unit of the later static report website.
- **Footer, every format:** "Facts only, not legal advice. Statuses: consistent / inconsistent / missing / unknown. No check decides whether you may use this data."
- **Badge** (`datasetdoctor badge report.json > badge.svg`): a local SVG in the shields style, generated without any web service. The text is factual, e.g. `datasetdoctor | 2 inconsistent · 1 dead link · full scan` or `datasetdoctor | no findings · sampled`. Colours: grey when nothing was found, amber for any `inconsistent`/`found`/`dead`, light grey for `unknown`-only. No green, because green reads as "safe".

## 8. Accuracy evaluation

**Answer key:** the Data Provenance Initiative's `data_summaries/*.json` in `github.com/Data-Provenance-Initiative/Data-Provenance-Collection`. It is in an Apache-2.0 repo, so we can use and redistribute it with attribution; the eval pins a commit sha. Measured today (§9):
- 109 summary files, **3,718 dataset entries**; 3,490 link to an HF dataset, but only **804 unique HF repos** (collections map many entries to one repo).
- Every entry has an expert `Licenses` list; 3,342 name a verifier (`License Verified By`).
- Each entry also records what the HF card said at audit time (`Inferred Metadata.HF Yaml License`, present for 3,133 HF-linked entries) and GitHub's licence (`GitHub License`, 1,279 entries).
- The DPI's own disclaimer says its licences are self-reported and categorised on a best-effort basis, so "agreement with DPI" is the metric, not "accuracy against truth".

**Building the key** (`eval/build_key.py`):
1. Map DPI licence names to SPDX with `data/dpi_licence_map.csv` (DPI's `license_paraphrases.json` plus hand mappings, each row reviewed). Terms that are not licences (`OpenAI` ToS, `Custom`, `Various`, `Non Commercial`, `Academic Research Purposes Only`) map to `non-SPDX`, and `Unspecified` / `No License` map to `none`.
2. Keep one key row per HF repo only when every DPI entry for that repo has the same expert licence set. Report how many repos this drops.
3. Expected status: card at audit time (`HF Yaml License`) vs expert set: equal -> `consistent`; both present and different -> `inconsistent`; YAML empty -> `missing`; expert `non-SPDX`/`none` -> excluded from Q3, counted separately.
4. Split by HF repo id hash: 30% dev (build tables, set the ScanCode threshold), 70% test. Freeze the config with a git tag before the test run.

**Measured questions:**
- **Q1 card parsing:** our C1 on the card *at the audit-time revision* (resolved via `/api/datasets/{id}/commits/main`, latest commit before the DPI summary's last-change date) vs `HF Yaml License`. Exact-match rate.
- **Q2 source licence detection:** our C4 for GitHub sources vs DPI `GitHub License` and vs the expert set. Agreement rate and `unknown` rate.
- **Q3 consistency status (headline):** our status vs the expected status, as a **4x4 confusion matrix** (consistent / inconsistent / missing / unknown; `unknown` is ours only), with:
  - agreement on decided rows, with a Wilson 95% interval;
  - Cohen's kappa;
  - the abstention (`unknown`) rate, reported separately so abstaining cannot inflate agreement;
  - precision and recall for `inconsistent`.
- **Disagreement audit:** the owner hand-labels 30 random disagreements as *ours wrong* / *key wrong* / *changed since audit* / *ambiguous*, and the counts are published with the matrix.
- Results go to `eval/results/RESULTS.md` in the tierview style: headline with its range, what it does and does not show, per-row data in JSON.

**Card-history caveat:** cards change after an audit. Q1 and Q3 use the audit-time revision to remove that drift. A separate, clearly labelled table shows today's cards vs DPI as "drift since audit", not as an error rate.

## 9. Feasibility evidence (measured 2026-11-19)

**Hugging Face Hub API** (anonymous, from this laptop):

| endpoint | result |
|---|---|
| `GET /api/datasets?sort=downloads&direction=-1&limit=N` | works; cursor pagination via `Link: <...&cursor=...>; rel="next"` |
| `GET /api/datasets/{id}` | returns `cardData` (parsed YAML incl. `license`, `source_datasets`, `dataset_info`), `siblings` (file list), `tags` (e.g. `license:other`), `sha`, `gated`, `downloads` |
| `GET /api/datasets/{id}/parquet` | config -> split -> Parquet URLs |
| `GET https://datasets-server.huggingface.co/parquet?dataset=` | file URLs with byte sizes, plus `partial` / `pending` / `failed` flags |
| `GET https://datasets-server.huggingface.co/size?dataset=` | rows and bytes per config/split (imdb: 100,000 rows, 83 MB Parquet) |
| `GET /datasets/{id}/resolve/main/README.md` | raw card (307 redirect to a cache URL) |

**Rate limits**, read from live response headers:

```text
RateLimit-Policy: "fixed window";"api";q=500;w=300        (Hub API)
RateLimit-Policy: "fixed window";"resolvers";q=3000;w=300 (file downloads)
RateLimit: "api";r=499;t=209                               (remaining, seconds to reset)
```

HF's published tiers (docs, "September '25"; anonymous and free values "subject to change"): anonymous per IP 500 API / 3,000 resolvers / 100 pages per 5 min; **free account 1,000 / 5,000 / 200**; PRO 2,500 / 12,000 / 400. So **a free account's token doubles the API limit and raises file downloads by 67%.** The owner creates it and logs in with `huggingface-cli login`; the tool picks the token up from there and never sees it typed.

The Dataset Viewer (`datasets-server`) sent **no** RateLimit headers, so its limits are undocumented. The launch scan throttles it conservatively and records 429s (task 4.2).

**Scale warning:** `HuggingFaceFW/fineweb-edu` is 2,410 Parquet files, 4,523 GB. Top-downloaded datasets include web-scale corpora, so the 5 GB full-scan limit matters.

**ScanCode on Windows:**
- In a venv under the long temp path, `pip install scancode-toolkit-mini` **failed** with `OSError: No such file or directory ... licensedcode\data\rules\epl-2.0_or_apache-2.0_or_gpl-2.0_with_classpath-exception-...RULE` and pip's hint that Windows Long Path support is not enabled.
- Retried at a short path (`C:\Users\melsa\.ddsc`): install succeeded in 116 s, and the venv was **637 MB** (652 MB with the plugin below; 79 packages). It then needed two fixes before it ran:
  1. `pluggy` 1.7.0 (pulled in by default) breaks `plugincode` 32.0.0 on import (`ValueError: did not find any 'plugincode.location_provider' hooks`). **Pin `pluggy<1.6`.**
  2. `-mini` ships no libmagic. In PowerShell it fails with `NoMagicLibError`; in Git Bash it finds Git's MSYS libmagic and **segfaults**. **Install `typecode-libmagic`** (has a `win_amd64` wheel).
- After both fixes, in PowerShell: `get_licenses()` detected `CC-BY-NC-4.0` from a prose README notice, `MIT` from `## License\nMIT`, and `CC-BY-SA-4.0` from a card's YAML `license: cc-by-sa-4.0` line. Index load took 3.6–5.7 s; each later file took under 0.1 s.
- That last result is why C2 strips the YAML before scanning: otherwise the card field would be counted twice.
- The test venvs were deleted afterwards. The `[scan]` extra must pin `pluggy<1.6` and add `typecode-libmagic` on Windows (task 3.4).

**DPI answer key:** repo licence Apache-2.0 (GitHub API), last push 2025-03-26, 285 stars; the numbers are in §8. The DPI's HF datasets carry no licence tag (empty `license:` tags), so we use the GitHub repo.

## 10. Launch scan: top ~500 HF datasets

**Goal:** a public table of facts for the 500 most-downloaded HF datasets, with a note on what was not checked.

1. **Freeze the list.** Page through `/api/datasets?sort=downloads&direction=-1` until 500 eligible datasets are listed, and save `launch/lists/top500-YYYY-MM-DD.json` (id, sha, downloads, gated, size). Skip `disabled` and private repos. Gated repos get card, licence, provenance and link checks only, because we never accept terms on the owner's behalf.
2. **Budget first (task 4.1).** Sum `/size` over the list before downloading anything. Two tiers:
   - Tier A, all 500: card, licence, provenance, links. No data download.
   - Tier B: data health with the normal planner, but with a launch-scan byte limit chosen from the measured budget (proposal: full scan up to 1 GB, sampled above), stated in the results.
3. **Rate-limit-friendly batching:**
   - One `http.py` limiter per bucket (api, resolvers, datasets-server, github) reads `RateLimit` (`r`, `t`) on every response and pauses when `r` falls under 20% of `q`.
   - On 429 it sleeps until `t` (or `Retry-After`), then retries at most 3 times.
   - About 4 API calls per dataset, so anonymous 500/5 min at a 50% target is about 60 datasets per 5 minutes and Tier A takes about 45 minutes (about 22 minutes with a free token).
   - GitHub: anonymous API is 60 requests/hour, so licence files are read from `raw.githubusercontent.com` (LICENSE, LICENSE.md, LICENSE.txt, COPYING at `HEAD`). GitHub's detected licence is fetched only when `GITHUB_TOKEN` is set, otherwise marked `not fetched`.
   - Batches of 25 datasets, with a checkpoint after each.
4. **Resumable.** `launch/state.sqlite` (stdlib `sqlite3`) has a row per `(dataset_id, sha, check)` with status, result JSON, error and finish time, plus the run's config hash. `launch run --resume` skips finished rows whose sha and config hash match. Ctrl-C finishes the current dataset and exits cleanly. A crash loses at most one dataset.
5. **Outputs:** per-dataset JSON + HTML, `launch/results/RESULTS.md` (counts of each status per check, with ranges where it is a rate), and a CSV. No dataset is called good or bad. The table is facts with links, and maintainers get a short note on how to re-check after fixing.

## 11. Phased task list

Each task is small, has a check you can run, and names its files. Tests never touch the network unless marked `network`.

### Phase 2: core checks without licences (Sonnet 5.5, medium)

| # | task | files | done when |
|---|---|---|---|
| 2.1 | Models and statuses: dataclasses, enums, JSON round-trip | `model.py`, `tests/test_model.py` | round-trip test passes; status enums match §5 exactly |
| 2.2 | HTTP layer: RateLimit-header limiter, retries, on-disk cache, user agent without personal data | `http.py`, `tests/test_http.py` | tests with fake responses: pauses at r < 20% q, honours `t` on 429, cache hit skips network |
| 2.3 | Hub adapter protocol + registry | `hubs/base.py`, `tests/test_registry.py` | `hf:x/y` and HF URLs resolve to the HF adapter; unknown ref gives a clear error |
| 2.4 | HF adapter: resolve sha, card, files, splits (`/parquet`, `/size`, `partial`) | `hubs/huggingface.py`, `tests/fixtures/hf/*`, `tests/test_hf_adapter.py` | offline tests on recorded imdb + one gated + one no-conversion fixture; one `network` test |
| 2.5 | Card check (all fields in §5.1 except SPDX validity, which is 3.1) | `checks/card.py`, `tests/test_card.py` | each rule has a passing and a failing fixture card |
| 2.6 | Link check | `checks/links.py`, `tests/test_links.py` | status table in §5.4 reproduced with a local test server |
| 2.7 | Canonical row encoding + xxh3_128 | `checks/health/rowhash.py`, `tests/test_rowhash.py` | equal rows hash equal across column order; 1 vs 1.0 vs "1" differ; nested and binary values covered |
| 2.8 | Scan planner + streaming reader (full / deterministic sample, one file at a time) | `checks/health/scan.py`, `tests/test_scan.py` | same seed gives the same sample; header text "Full scan" / "Sampled: N of M rows" |
| 2.9 | Duplicates + cross-split leakage on DuckDB (on disk) | `checks/health/duplicates.py`, `tests/test_duplicates.py` | synthetic splits with known dup/leak counts match exactly; works when data exceeds a tiny memory cap |
| 2.10 | Empty rows, corrupt files, label balance | `checks/health/empty.py`, `labels.py`, tests | synthetic fixtures; corrupt Parquet file reported, scan continues |
| 2.11 | PII pattern matcher with masking | `checks/health/pii.py`, `tests/test_pii.py` | precision fixtures (non-emails, version numbers, dates not matched); masking never prints the full value |
| 2.12 | JSON + terminal report; CLI `check` | `report/json_out.py`, `report/terminal.py`, `cli.py` | `datasetdoctor check hf:stanfordnlp/imdb` runs end to end on the laptop; scan time and throughput logged to BUILD_LOG |
| 2.13 | CI: lint, type check, tests on Windows + Ubuntu, Python 3.11/3.12/3.13 | `.github/workflows/ci.yml` | green on a branch (pushed only with the owner's OK) |

### Phase 3: licence + provenance (Opus 5.5, high)

| # | task | files | done when |
|---|---|---|---|
| 3.1 | HF licence id table from HF's published list, each row with an SPDX id / family / non-SPDX tag | `data/hf_licence_ids.csv`, `licences/hf_ids.py`, tests | every id on HF's list is mapped; a test fails if the list gains an unmapped id (network test) |
| 3.2 | SPDX wrapper: parse, normalise, equivalence, subset | `licences/spdx.py`, tests | `MIT` vs `mit` consistent; `MIT` vs `MIT AND CC-BY-4.0` gives subset; `GPL-2.0` vs `GPL-2.0-only` handled as SPDX defines |
| 3.3 | Licence properties: SPDX flags + CC elements; confirm the SPDX list data's own licence | `licences/properties.py`, `data/cc_elements.csv`, tests | every CC licence on HF's list has BY/SA/NC/ND with its deed URL; no other property is emitted |
| 3.4 | ScanCode wrapper as the `[scan]` extra; graceful absence | `licences/scanner.py`, `pyproject.toml`, tests | README notice, LICENSE file and "## License\nMIT" fixtures detected; without the extra, status `unknown (scanner not installed)` |
| 3.5 | GitHub + web source resolvers (raw LICENSE files; optional token API) | `hubs/github.py`, `hubs/web.py`, fixtures | anonymous path makes zero `api.github.com` calls; token path labelled |
| 3.6 | Licence consistency check (C1 vs C2/C3/C4, §5.2) | `checks/licence.py`, tests | one fixture per status and sub-fact; report sentences match the §5.2 example format |
| 3.7 | Provenance check (declared parents, depth 2, cycles, cross-hub refs) | `checks/provenance.py`, tests | parent-licence mismatch fixture; cycle fixture terminates; `original` gives no parent |
| 3.8 | Windows install guidance for the extra + CI job installing it on Windows at a short path | `docs/INSTALL.md`, `ci.yml` | CI installs `[scan]` on windows-latest and runs the scanner tests |

### Phase 4: accuracy evaluation + launch scan (Opus 5.5, high)

| # | task | files | done when |
|---|---|---|---|
| 4.1 | Launch budget: freeze top-500 list, sum sizes, propose the Tier B limit | `launch/freeze_list.py`, `launch/lists/` | list saved; total bytes and request estimate written to BUILD_LOG |
| 4.2 | Resumable runner with SQLite state, batching, limiter, Ctrl-C safety | `launch/run.py`, `launch/state.py`, tests | killing the process mid-batch and resuming finishes with no duplicate or missing rows (test) |
| 4.3 | DPI key builder (pinned sha), licence-name map, dev/test split | `eval/build_key.py`, `data/dpi_licence_map.csv` | key stats match §8 counts; dropped-repo count reported |
| 4.4 | Audit-time card revision lookup | `eval/revisions.py` | for 20 dev repos the chosen commit predates the DPI file date (test) |
| 4.5 | Dev run, tune ScanCode threshold only, then freeze config (git tag `eval-config-v1`) | `eval/run.py`, `eval/config.yml` | tag exists before any test-split result is computed |
| 4.6 | Test run + metrics: confusion matrix, Wilson CI, kappa, abstention, inconsistent P/R | `eval/metrics.py`, `eval/results/` | `RESULTS.md` written in tierview style; owner labels 30 disagreements |
| 4.7 | Launch scan Tier A then Tier B | `launch/results/` | RESULTS.md with per-status counts, not-checked list and run dates |

### Phase 5: polish, Action, README, launch (Sonnet 5.5, medium)

| # | task | files | done when |
|---|---|---|---|
| 5.1 | Markdown + HTML report (static, no JS) | `report/markdown.py`, `report/html.py` | snapshot tests; HTML renders offline |
| 5.2 | Badge SVG | `report/badge.py` | snapshot tests for each colour rule; no "safe/pass" wording (test greps for banned words) |
| 5.3 | Banned-words test across all outputs ("safe", "compliant", "legal to", "allowed", "you may") | `tests/test_wording.py` | fails if any renderer emits them |
| 5.4 | GitHub Action (composite, Python) that runs `check` on a dataset ref and uploads the report | `action.yml`, `examples/workflow.yml` | runs on a test repo (only after the owner OKs pushing) |
| 5.5 | Static report website from launch-scan JSON (plain HTML, GitHub Pages later) | `site/build.py` | builds locally; no external requests |
| 5.6 | Optional AI summary, off by default, labelled "AI summary, not part of the checks", input = report JSON only; free path via the owner's `claude` CLI | `summary.py` | absent unless `--ai-summary`; never changes a status (test) |
| 5.7 | README in tierview style: headline numbers from 4.6 with ranges, what it does not show, not-legal-advice notice | `README.md` | every number links to RESULTS.md |
| 5.8 | Re-run the competitor check; PyPI release dry run (`twine check`) | `BUILD_LOG.md` | logged; nothing published without the owner's OK |

## 12. Risks and open questions

- **Name** (§1): keep `datasetdoctor` or rename. Owner decides before Phase 2.
- **ScanCode on Windows**: long paths. Mitigated by the optional extra and docs; CI proves it (3.8).
- **The DPI key is a snapshot of self-reported, best-effort labels** (their own disclaimer). We publish agreement, not accuracy, plus the disagreement audit.
- **Dataset Viewer limits are undocumented**: measured during 4.1/4.7.
- **Launch-scan bandwidth**: unknown until 4.1 sums the sizes; Tier B's limit is set from that, not guessed.
- **PII regexes** will have false positives and misses; the output says "pattern matches", and 2.11's fixtures measure precision on known non-PII strings. No recall claim is made.
- **Licence properties**: SPDX data carries no NC/SA properties for non-CC licences, so those show none. This is narrower than the brief's wording; owner to confirm.
