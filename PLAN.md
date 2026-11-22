# datasetvet: plan

> **Before you train on it, check it.**
> A CLI that checks a dataset and writes a report card of verifiable facts: what the card says, what the licence files and the source say, whether the links work, and what is in the data (duplicates, cross-split leakage, empty rows, label balance, PII-pattern matches). It never says a dataset is "safe to use", and it is not legal advice.

Status: **Phase 4.5 (fixes from the launch scan, rescan) complete, 2026-11-22**; results in [RESULTS.md](RESULTS.md). Phase 3's full licence texts were removed from all git history before any push (§12; commit ids in BUILD_LOG). Implemented: card check (with HF-id/SPDX validity), licence consistency (C1 vs C2/C3/C4), provenance, a built-in SPDX licence matcher, the optional ScanCode scanner, GitHub and web source resolvers, links, data health, the Hugging Face adapter, JSON and terminal reports. Phase 4.5: paged file lists past 100,000 entries ("Partial scan" when incomplete), three reader bug fixes, the "files that could not be read as rows" check, non-data files skipped. Also built in Phase 4: the eval harness (`eval/`), the launch scan (`launch/`), the SPDX fingerprint index (no licence texts shipped) and faster data fetching (git pack, parallel downloads). Not implemented: Phase 5. Where Phase 2, 3, 4 or 4.5 changed or clarified this plan, the section says so ("Phase 2:", "Phase 3:", "Phase 4:", "Phase 4.5:"). Every "measured" figure in this file was measured on 2026-11-19 from this laptop (Windows 11, Python 3.12.10) and is listed with how it was measured in [Feasibility evidence](#9-feasibility-evidence-measured-2026-11-19).

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

**Decision (owner, 2026-11-19): `datasetvet`.** Re-checked the same day: free on PyPI and npm, no GitHub user or org, 0 GitHub repos. Package `src/datasetvet/`, CLI `datasetvet`. The tagline stays "Before you train on it, check it."

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
src/datasetvet/
  cli.py                 argparse entry point: `datasetvet check <ref>`, `datasetvet badge`
  config.py              limits (scan bytes, sample size, timeouts), loaded from flags/env/file
  model.py               dataclasses: DatasetRef, Evidence, Fact, CheckResult, Report; status enums
  http.py                one session: RateLimit-header limiter, retries, on-disk cache, user agent
  hubs/
    base.py              HubAdapter protocol, SourceResolver protocol, registry
    huggingface.py       v1 adapter
    github.py            v1: source resolver (licence of a GitHub repo); v2: dataset adapter
    web.py               plain-URL source resolver (link status only + licence text if a licence page)
  licences/
    spdx.py              SPDX list metadata (no texts) + license-expression wrapper; parse, normalise, compare
    hf_ids.py            HF licence id -> SPDX id / family / non-SPDX table (data/hf_licence_ids.csv)
    matcher.py           Phase 3: built-in matcher (full texts, notices, licence URLs; no AI)
    scanner.py           Scanner interface: builtin, or ScanCode (optional extra)
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
  data/                  hand-checked tables (CSV) with a source URL per row; SPDX metadata + fingerprint index
tools/vendor_spdx.py     rebuilds the SPDX metadata and the matcher's fingerprint index from a pinned SPDX release (Phase 4: no texts shipped)
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
| `license-expression` (+ `boolean.py`) | SPDX parse/normalise/equivalence (1.5 MB installed) | Apache-2.0 (+ BSD-2-Clause) |
| SPDX licence list 3.29.0, derived data only (Phase 4) | metadata for 740 ids (8.5 KB gzipped) and a hashed-bigram fingerprint index of 92 texts (281 KB); no licence text | see §12: the list's own licence is not stated |
| `pyyaml` | card front matter | MIT |
| `phonenumbers` | phone-number validation after regex candidates | Apache-2.0 |
| `rich` | terminal report | MIT |
| extra `[scan]`: `scancode-toolkit-mini`, `pluggy<1.6`, `typecode-libmagic` (Windows) | licence text detection (§4) | Apache-2.0 AND CC-BY-4.0 (data) |

Tokens: an HF token or a GitHub token is read only from the user's own environment (`HF_TOKEN`, `huggingface-cli login` storage, `GITHUB_TOKEN`). The tool never asks for, prints, logs or stores a token, and reports show only "authenticated: yes/no".

## 4. Licence scanner choice

| scanner | accuracy on our inputs | Windows | install weight | licence | maintained |
|---|---|---|---|---|---|
| **ScanCode toolkit** (`scancode-toolkit-mini` 32.5.0) | Detects full licence texts **and** notices/references inside prose ("released under CC BY-NC 4.0", "## License\nMIT") using ~2,300 curated licences and tens of thousands of rules; returns SPDX expressions, match scores and line numbers | works on this laptop after 3 measured fixes (§9): short venv path (MAX_PATH), `pluggy<1.6`, `typecode-libmagic` | 120 MB wheel; **652 MB venv** | Apache-2.0 (code), CC-BY-4.0 (licence data) | release 2026-01-15, pushed 2026-11-11, 2,676 stars |
| askalono (Rust CLI) | Full licence texts only (Dice similarity over normalised text); not designed for notices inside READMEs | Windows binary in releases | single small binary | Apache-2.0 | last release 0.5.0, 2024-10-22; no PyPI package |
| licensee (Ruby; what GitHub's API uses) | LICENSE files and a README "License" section; small licence set (choosealicense.com) | needs a Ruby toolchain | Ruby + gems | MIT | active (pushed 2026-11-16) |
| SPDX licence-list template matching | Exact-ish full-text matching against SPDX templates; strict and slow, no notice detection | any | small | SPDX data (licence: repo reports NOASSERTION; to verify) | active |

**Recommendation: ScanCode toolkit**, installed as an optional extra (`pip install datasetvet[scan]`).

~~The default install has no licence-text scanner~~ (decision of 2026-11-19, before Phase 2; **replaced by the owner's Phase 3 decision below**).

**Phase 3 decision (owner, 2026-11-19): the plain install gets a built-in licence matcher.** Deterministic, matching against official SPDX licence texts (askalono-style), no AI, small and dependency-light. As built (`licences/matcher.py`, standard library only):
- **Data:** 92 official texts from `spdx/license-list-data` tag v3.29.0 (every SPDX licence HF's id list maps to, plus other versions of the same families and common data licences), and the OSI/FSF/deprecated flags of all 740 ids. Texts that are identical after normalisation form one group (GPL-2.0-only / GPL-2.0-or-later and 4 more pairs), so 87 groups.
- **Phase 4 decision (owner, 2026-11-19): no licence texts are shipped.** The package carries only the list metadata (`spdx_licences.json.gz`, 8.5 KB) and a fingerprint index (`spdx_fingerprints.json.gz`, 281 KB): per group, the multiset of 64-bit BLAKE2b hashes of its normalised word bigrams and its word count, delta-encoded against one shared hash table. No word is stored. `tools/vendor_spdx.py` downloads the texts from the pinned tag into a git-ignored cache and regenerates both files; `--check` rebuilds them byte for byte (CI runs it). The matcher hashes the input text's bigrams the same way, so its scores are unchanged (all matcher tests pass against the index). Tests that need a real licence text read the cache and are skipped without it.
- **Full text:** normalisation along the SPDX matching guidelines (case, quotes, dashes, copyright lines, SPDX's `equivalentwords.txt`), word bigrams counted as a multiset. A text *is* licence L when Dice >= 0.90; it *contains* L (e.g. a README with the MIT text under "## License") when containment >= 0.95, and when two contained licences overlap the larger wins (MIT inside X11). Multiset rather than set bigrams were needed: as sets, CC-BY-1.0 and CC-BY-SA-1.0 scored 0.997 against each other; as multisets every one of the 92 texts identifies itself and close relatives (MIT/MIT-0/X11, ISC/0BSD, BSD-2/3, CC-BY/BY-SA 1.0 and 4.0, GPL-3.0/AGPL-3.0) are told apart (tests).
- **Notices:** `SPDX-License-Identifier:` lines, and licence names and ids from the SPDX list plus common short forms ("CC BY-NC 4.0", "Apache 2.0", "GPLv3", "CC0", "ODC-BY") inside a licence context: a "License:" line, a section headed License/Licensing, or within 25 words of "license"/"licence" or "released/distributed/available ... under". One-word names (MIT, ISC, Unlicense) need the word license within 3 words. A Creative Commons name without a version ("CC BY-SA") is flagged and never compared.
- **Licence URLs:** creativecommons.org licence and deed URLs (ports only when the port is on the SPDX list), gnu.org, opendatacommons.org, spdx.org / opensource.org / choosealicense.com id URLs, and every `seeAlso` URL the SPDX list publishes. The URL itself is the evidence; it is not fetched.
- **Not covered:** licences that are not on the SPDX list (Llama, OpenRAIL, custom terms), and free-text paraphrases ("for research use only"). Those give no detection, so the comparison is `missing` or `unknown`, never a guess.
- Thresholds are fixed in code and may only be tuned on the Phase 4 dev split.

**Scanner choice:** `--scanner builtin | scancode | auto` (default `auto`: ScanCode when it imports, else built-in). Every report names the scanner and version it used. ScanCode detections are kept at score >= 90 (`SCANCODE_MIN_SCORE`). Phase 4: the dev split chose 50 (76 of 116 dev rows agree at 50, 66 at 90); the frozen eval config uses 50, the code default is still 90 until the owner decides (BUILD_LOG Phase 4).

The accuracy evaluation reports the two configurations separately (§8): `builtin` and `scancode`, on the same answer key, so the cost of skipping the 652 MB extra is measured, not assumed.

- It is the only option that handles our hardest input, licence *statements inside dataset READMEs and web pages*, not just LICENSE files.
- It is deterministic and gives a score and the matched lines, which become the report's evidence.
- Its licence keys and SPDX mappings come from the same project as `license-expression`, so normalisation and comparison use one consistent licence database.

Costs and how we contain them:
- **Weight.** The core install (card check, SPDX validation, built-in matcher, links, data health) does not need ScanCode. Without the extra, the built-in matcher reads the texts (Phase 3).
- **Windows install.** The extra pins `pluggy<1.6` and adds `typecode-libmagic` on Windows. The install docs say to enable long paths or create the venv at a short path such as `C:\dd\.venv`, and to run from PowerShell, not Git Bash (Git's libmagic segfaults ScanCode). CI tests the extra on Windows.
- **Cross-check, not a second opinion.** For GitHub sources we also record GitHub's own detected licence (`/repos/{o}/{r}/license`, which is licensee) as a separate, labelled fact. If our scanner (built-in or ScanCode) and GitHub disagree, both are shown and the status is `unknown`, never a guess.

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

Phase 2 clarifications, from the live test cards:
- **Stated source** also counts labelled Markdown links anywhere in the body, e.g. `[Website](…) | [Paper](…) | [GitHub](…)`, when the link text starts with Homepage, Repository, Paper, Point of Contact, Source, Website, Code, Download, Data, Project page or GitHub. Unlabelled links (`[Center for AI Safety](…)`) are not stated sources and are not link-checked.
- **Citation:** a heading containing "citation" (emoji and other prefixes allowed) with no code block, DOI, arXiv id or BibTeX is still `missing`, but the fact says the heading exists and may point elsewhere.
- **Language** is required when the Hub tags say `modality:text` or give no modality; it is skipped when the tags list only non-text modalities.
- **Gated cards:** if the README cannot be read, citation and README-bullet sources are listed under "not checked" instead of being reported `missing`.

HF family ids (`bsd`, `cc`, `gpl`, `lgpl`, `gfdl`, `openrail`) are reported as "a family, not a specific licence": the card check is `present`, but every consistency comparison involving them is `unknown`.

Phase 3, as built (task 3.1): `data/hf_licence_ids.csv` maps all 83 ids on HF's list (hub-docs commit `fd6cf1f`, 2026-06-06) to `spdx` (53), `family` (8: also `odc-by` and `odbl`, which HF itself names as families), `non-spdx` (20: Llama, Gemma, OpenRAIL-M, ...) or `special` (2: `unknown`, `other`). Five HF ids map to deprecated SPDX ids (`gpl-2.0` -> `GPL-2.0`, also gpl-3.0, lgpl-2.1, lgpl-3.0, agpl-3.0); `license-expression` treats those as the `-only` variants, as SPDX did. A value that is not an HF id but is an SPDX id (e.g. `ODC-By-1.0`) is `present` with that fact; anything else is `invalid`. A network test fails if HF's list gains an unmapped id.

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

Phase 3, as built (`checks/licence.py`):
- **One result per comparison**: card vs README text, card vs each licence file, card vs each source file / licence URL / HF dataset. Each sentence reads e.g. `Card says mit (SPDX MIT) (README.md@878c103, YAML line 8); github.com/robinjia/adversarial-squad LICENSE@9cd77aa says MIT (full text, score 100, lines 1-21); these are the same licence.` Properties of the other side's licence follow when it differs from the card's.
- **Card side.** A card list (`[mit, cc-by-4.0]`) is compared as one set (`MIT AND CC-BY-4.0`); HF does not say whether a list means AND or OR. `unknown`/empty is `missing`. Family ids, `other` (with or without `license_name`) and values that are neither HF nor SPDX ids make every comparison `unknown`. Non-SPDX HF ids become `LicenseRef-hf-<id>` and compare by exact name only.
- **Several licences in one place** (a README naming MIT for code and CC-BY-4.0 for data): `consistent` only if together they equal the card's set; otherwise `unknown` (plus "None of these is the card's licence" when that is true). One expression with AND that strictly contains the card's licence is `inconsistent` / `subset`, as specified.
- **Identical texts**: a GPL-2.0 text matches a card's `GPL-2.0-only` or `GPL-2.0-or-later`; the fact says the text alone does not say which.
- **README (C2)**: `missing` when the README body never mentions a licence, or when its only licence content is HF's template placeholder `[More Information Needed]` (TOC lines ignored); `unknown` when it mentions a licence and nothing is identified.
- **Licence files (C3)**: `LICEN[CS]E*`, `COPYING*`, `*.license` anywhere in the repo, up to 10, first 512 KB each. A repo with none gets no result, only a "not checked: nothing to compare" line.
- **Sources (C4)**: stated sources (Homepage, Repository, ... bullets and labelled links) and the card's `license_link`, minus `source_datasets` (provenance's job), the dataset's own repo, duplicate links to the same GitHub repo / HF dataset, and HF's old card-template link (`github.com/huggingface/datasets/blob/*/CONTRIBUTING.md`, which many legacy cards give as "Repository"). Up to 10 sources. Papers and homepages are listed as "not read for a licence".
- **GitHub, anonymous** (`hubs/github.py`): HEAD pinned via git's smart-HTTP ref advertisement (`github.com/{o}/{r}.git/info/refs`, not API-limited), then raw files at that sha: the first of `LICENSE, LICENSE.md, LICENSE.txt, LICENCE, COPYING`, plus `DATA_LICENSE` and `LICENSE-DATA` (tatsu-lab/alpaca keeps its data licence there). Zero `api.github.com` calls (test). With no file found the status is `unknown` ("other file names are not checked without GITHUB_TOKEN"), because the anonymous path cannot list a repo; with `GITHUB_TOKEN`, GitHub's API saying "no licence" too makes it `missing`.
- **Web** (`hubs/web.py`): a licence's own URL is a claim without fetching; a page whose path contains license/licence/terms/copyright/legal is fetched (512 KB), HTML reduced to text, and scanned; other pages are not read.

**Licence properties** (shown next to each licence, never used to decide anything):
- From the SPDX licence list: OSI-approved, FSF-libre, deprecated id.
- For Creative Commons licences only: the licence elements BY / SA / NC / ND, which are part of each licence's published name and deed (creativecommons.org). Kept in `data/cc_elements.csv` with the deed URL per row.
- Nothing else. The SPDX list does **not** publish properties such as "non-commercial" for non-CC licences, so for those the report shows no property rather than an interpretation. (This narrows design rule 1's "properties via SPDX data": SPDX data alone does not carry NC/SA.)

### 5.3 Provenance (never sampled)

- **Parents** are only *declared* derivations: YAML `source_datasets` entries that resolve to a dataset (`extended|<id>`, an HF repo id, or a URL another adapter can resolve). README links to other datasets are listed as "mentioned", never treated as parents.
- For each parent: resolve with the matching adapter (cross-hub allowed), read its C1 (and C3 where cheap), compare with the child's C1 using the §5.2 rule and statuses, and show both licences' properties side by side.
- Depth limit 2 by default (`--provenance-depth`), cycle detection by `(hub, id)`, every parent pinned to a revision.
- Unresolvable parent (`original`, `extended|other-foo`, free text) -> `unknown`, with the raw value shown.

Phase 3, as built (`checks/provenance.py`):
- `original` is not a parent. With no declared parents there is no provenance result; the report's "Not checked" list says why and names any HF datasets the README mentions (not treated as parents).
- Legacy ids resolve through the Hub's redirect (`extended|squad` -> `rajpurkar/squad`, `glue` -> `nyu-mll/glue`), and the fact says so. A missing parent is `unknown` with the Hub's error.
- At depth 2 each grandparent is compared with its own child (the parent), so every edge of the chain gets one status; the title says "parent of X".
- A parent given as a URL goes through the GitHub or web resolver and the scanner, the same way as a C4 source.

### 5.4 Links (never sampled)

- Targets: every stated source URL, `license_link`, URLs in the card's metadata fields, and repo files referenced from the card (`configs[].data_files` paths that do not exist in the file list -> "missing file").
- Method: `HEAD`, falling back to `GET` with a 64 KB cap; follow up to 5 redirects; timeout 15 s; 2 retries with backoff; one request per host per second; obey `robots.txt` for non-API hosts.

| status | rule |
|---|---|
| `ok` | final response 2xx |
| `dead` | 404 or 410, or DNS NXDOMAIN; missing repo file |
| `restricted` | 401, 403, 451, or an HF gated repo |
| `unreachable` | timeout / connection error after retries, or 5xx after retries |
| `unknown` | 429 that did not clear, or 3xx loops; also (Phase 2) robots.txt disallows the URL, or any other status code (e.g. 400, 418) |

The report shows the final URL and status code. A dead link is a fact about today; the report says when it was checked.

### 5.5 Data health (full scan by default)

**Data source per split:** HF's Parquet conversion (`refs/convert/parquet`) when it exists and its `/parquet` response has `partial: false`; otherwise the original files if they are Parquet, CSV or JSON Lines; otherwise `not checked (unsupported format)`.

**Scan planner:** total bytes from the Dataset Viewer `/size` endpoint (or the file list).
- `bytes <= 5 GB` (default `--max-scan-bytes 5GB`): **Full scan**, every row of every split.
- Above the limit: **deterministic sample**: whole Parquet row groups chosen with a fixed seed (recorded in the report), stratified so every split and file contributes in proportion to its rows, up to `--sample-rows 1,000,000`. The report header says `Sampled: N of M rows (seed S)`.
- Files are downloaded to a temp dir and deleted after reading (one resolver request per file, not many range reads), so disk use is bounded by the largest file plus the files fetched ahead (Phase 4: see "Fetch routes" below).
- 5 GB: a full scan on a laptop is mostly download time (about 7 minutes at 100 Mbit/s; measured throughput is a Phase 2 task). Above it, a default run could take hours, so the user opts in with `--full`.

Phase 2, as built (`checks/health/scan.py`, `hubs/huggingface.py`):
- **Sampling detail.** Each split's quota is proportional to its rows. Within a split, files are visited in a seeded order until the quota is met. Not every file contributes: per-file range reads would multiply requests. Each chosen file is downloaded whole, so a split stored in one file costs its full download even when sampled.
- ~~Whole Parquet row groups are taken in a seeded order~~ (Phase 2). **Phase 3 (owner decision): many small chunks spread across each file.** Each file read is cut into slots of `min(100, quota // 100)` rows (at least 1), and slots are drawn with the seed until the file's share of the quota is met, so a split's sample comes from about 100 or more chunks across the whole file. Only row groups holding a chosen chunk are decoded. CSV/JSON Lines files are counted in a first pass and sampled the same way. The scan reason says "rows are read in small chunks spread across each file read".
- **Clusters.** On IMDB train (one file, sorted by label) a 5,000-row sample showed 70/30 labels with row groups against the true 50/50; with chunks it shows 51.8/48.2 (seed 0, measured 2026-11-19). Files themselves can still be ordered (e.g. one label per file), so the label table keeps its warning whenever the scan is sampled, now naming the chunk size.
- **Conversion pinned.** Parquet files are read from the `refs/convert/parquet` commit sha (from `/api/datasets/{id}/refs`), not the moving ref. The Hub does not say which main revision a conversion was built from.
- **Original-files fallback** reads Parquet, CSV, TSV, JSON Lines and JSON (optionally `.gz`), mapped to splits by the card's `configs` or HF's file-name convention, and never reads hidden paths (`.metadata/…`). If the owner disabled the Dataset Viewer and the card has no `configs`, data health is `not checked`: nothing states which files are data.
- **Gated datasets:** data health is `not checked`; the tool never accepts terms.
- **File list (Phase 4.5, `HuggingFaceAdapter.listing`).** The Hub's dataset API returns at most 100,000 entries in `siblings`. A list of that size is read again through the paged tree API (`/api/datasets/{id}/tree/{sha}?recursive=true`, 1,000 entries a page, following the `Link: rel="next"` header; the next link must stay on huggingface.co and a repeated page stops the loop). If that fails (HTTP error, loop, more than 5,000 pages), the listing is `complete=False`, nothing treats it as the whole repo, and:
  - a scan built from it is headed **"Partial scan: the repo's file list is incomplete"**, never "Full scan" (a sample says "(partial file list: the sample drew from part of the repo)"), and `ScanInfo.listing_complete` is false;
  - a card `data_files` path that matches nothing is **not** reported as a missing file; the report's `not_checked` says how many paths could not be verified;
  - the licence-file search says it may have missed a file;
  - the git pack route is not used.
- **Files that are not data (Phase 4.5).** When the card's `configs` name no files, every Parquet/CSV/JSON file is a guess at "data". Tokenizer, model and package configuration (`config.json`, `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `vocab.json`, `generation_config.json`, `dataset_infos.json`, `package.json`, `tsconfig.json`, `*.index.json`, ...) and anything under `site-packages`, `dist-packages`, `node_modules` or `__pycache__` are skipped, and the report's data notes say how many were skipped and name the first five. A file the card names in `configs` is always read. If nothing is left, data health is `not checked` and says why.
- **JSON reading (Phase 4.5).** pyarrow's JSON reader is used first. Python's own parser reads the file instead when pyarrow's result fails `validate(full=True)` (it builds an invalid array for some nested null lists: `ArrowIndexError` on conversion) or stops on a block-size limit. A JSON array whose items are all non-objects (strings, numbers, lists) gives one row per item in a column named `value`; an array mixing objects and non-objects is a file that could not be read as rows. Empty files stay `empty`.
- **Nanosecond timestamps (Phase 4.5).** A `timestamp[ns]` column whose values are not whole microseconds cannot be a Python `datetime`; such columns (also inside structs and lists) are hashed as their integer count of nanoseconds, so values one nanosecond apart still differ. Mixed units for one column across files would hash differently; not handled.
- **One file does not stop a dataset (Phase 4.5).** A batch that cannot be turned into values stops that file, is reported as a file that could not be read as rows, and the scan continues.
- **Fetch routes (Phase 4, `checks/health/fetching.py`, `hubs/gitpack.py`).** The Tier B launch scan spent 55 minutes on one repo of 5,410 small files: one HTTP request (about 0.3–1 s) per file, with no 429s. Two routes now get files to the same reader faster, and neither changes what is read:
  - *git pack:* for original files at a pinned commit, when at least 20 data files are plain git blobs (not LFS, at most 10 MB) and the Hub's listed sizes bound the whole fetch to 256 MB (and to the download cap on a capped sample), one shallow `git fetch --filter=blob:limit=10m` of the commit brings every small blob in one packfile. A file is read from it only when the blob id equals the `blobId` the Hub lists for that path and the size matches; anything else, and any git failure, is downloaded over HTTP as before. A bare repo in the temp dir, no working copy, prompts and credential helpers off, https only. The Hub's git server answers only about 10 explicit blob ids per request, so "fetch only these files" is not used. Git is not used when the file list is incomplete (below), because the fetch size cannot then be bounded. `--no-git-fetch` / `DATASETVET_GIT_FETCH=0` turns it off.
  - *parallel:* other files are downloaded up to `--fetch-workers` (default 8) at a time ahead of the reader, in the reader's own order. A file is fetched ahead only when its size is known and, under a download cap, it still fits with everything read or in flight; a failed download raises the same error when the reader reaches that file. The Hub's download CDN (`*.hf.co`) is exempt from the one-request-per-second spacing for other hosts; RateLimit headers and 429s still apply.
  - *equivalence:* `launch/fetch_equivalence.py` reruns Tier B datasets and compares each report field by field with the report the one-file-at-a-time route made at the same revision (timings, request counts and the new `data_fetch` note excluded).
- **Leakage** compares splits within one config only. A ClassLabel value of `-1` means "no label": a split with only `-1` is not compared on labels, and `-1` is left out of the label ratio and the "absent from train" list.
- **DuckDB memory:** queries use only spillable operators (aggregates, joins, windows). Tested at a 64 MB cap with 1.1 M rows; DuckDB cannot run these joins at 32 MB.

**Row identity:** canonical encoding of each row: columns in sorted name order, each value type-tagged (null, bool, int, float as IEEE-754 bits, string as UTF-8, bytes, nested lists/structs recursively; images/audio as their raw bytes). Hash: xxh3_128. Two hashes per row:
- `row` (all columns), and
- `input` (all columns except label columns: `ClassLabel` features in `dataset_info`, else columns named `label`/`labels`), so "same text, different label" leakage is caught.
Collision bound stated in the report: about 1.5e-21 for 1e9 rows (birthday bound for 128 bits).

| sub-check | rule | output |
|---|---|---|
| within-split duplicates | rows sharing a `row` hash inside one split | count of extra copies, % of split, up to 5 example row indices |
| cross-split leakage | `input` hashes present in more than one split (e.g. train ∩ test) | count per split pair, % of the smaller split, examples; separately how many of those also differ in label |
| empty rows | every column null or empty string / empty list | count, examples |
| files that could not be read as rows (Phase 4.5: was "corrupt data") | a file fails to download, open or decode into a table | file path, error and a kind (`invalid`, `reader_limit`, `empty`, `download`); the split's other results are marked partial. It does not say the file is damaged: `reader_limit` means datasetvet's reader needs one type per column; non-data files (below) are never read, so they are never counted |
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

- Phase 2 changes to the adapter, as built in `hubs/base.py`:
  - `splits(ds, card=None)` returns a `DataPlan`: splits, plus a `not_checked` reason and notes;
  - `open_split` is replaced by `fetch(file, dest_dir) -> Path`, and reading/sampling lives in `checks/health/scan.py`, so every hub shares one reader;
  - `blob_url(ds, path, line)` builds evidence links;
  - `SourceResolver.link_status` is dropped, because the link checker handles every URL itself.
- Phase 3 change: `SourceResolver.licence_claims(url)` became `read(url) -> SourceRead` (licence texts to scan, structured claims such as GitHub's detection or a licence URL, a state: read / no licence file / unreadable / skipped, and the pinned revision), so every scanner reads the same texts.
- The registry tries adapters, then resolvers, in order; `ParentRef` carries a URL or `hub:id`, so an HF card can name a Zenodo record or GitHub repo as its parent and the provenance check follows it with the right adapter.
- v1 ships `huggingface` (adapter) plus `github` and `web` (resolvers).
- v2 notes, not verified in Phase 1: Zenodo has an open REST API with `metadata.license`; Kaggle's API needs a free API key (the user's own); a GitHub-hosted dataset adapter reuses the `github` resolver plus a file reader. Each needs its own feasibility check before work starts.

## 7. Report formats and badge

- **JSON** (`--json out.json`) is the single source of truth, with `schema_version`. It holds the tool version, ScanCode version and licence-DB version, the dataset ref and pinned sha, the scan type, the time, every fact with its evidence, and every status. All other formats render from it, so they cannot disagree.
- **Terminal:** one block per section: status word, the facts as one-line sentences, evidence links. The first line is the scan type and anything not checked.
- **Markdown** (`--md`), for PRs and issues, and **HTML** (`--html`): one static file, no JavaScript, no external requests, links to evidence. The HTML is the unit of the later static report website.
- **Footer, every format** (reworded in Phase 3 to pass the banned-words test): "Facts only, not legal advice. Licence statuses: consistent / inconsistent / missing / unknown. No check here judges how this data can be used." The banned phrases live in `model.BANNED_PHRASES`; `tests/test_wording.py` already checks the footer, the licence properties and rendered terminal reports (task 5.3 extends it to every renderer).
- **Badge** (`datasetvet badge report.json > badge.svg`): a local SVG in the shields style, generated without any web service. The text is factual, e.g. `datasetvet | 2 inconsistent · 1 dead link · full scan` or `datasetvet | no findings · sampled`. Colours: grey when nothing was found, amber for any `inconsistent`/`found`/`dead`, light grey for `unknown`-only. No green, because green reads as "safe".

## 8. Accuracy evaluation

**Answer key:** the Data Provenance Initiative's `data_summaries/*.json` in `github.com/Data-Provenance-Initiative/Data-Provenance-Collection`. It is in an Apache-2.0 repo, so we can use and redistribute it with attribution; the eval pins a commit sha. Measured today (§9):
- 109 summary files, **3,718 dataset entries**; 3,490 link to an HF dataset, but only **804 unique HF repos** (collections map many entries to one repo). Phase 4, as built: 3,492 entries and **792** unique repos; 81 dropped because their entries disagree, 3 with no recorded card licence, so **708 key rows**; Q3 keeps **371** (239 consistent, 80 inconsistent, 52 missing) after excluding 212 "none stated" and 125 non-SPDX expert licences.
- Every entry has an expert `Licenses` list; 3,342 name a verifier (`License Verified By`).
- Each entry also records what the HF card said at audit time (`Inferred Metadata.HF Yaml License`, present for 3,133 HF-linked entries) and GitHub's licence (`GitHub License`, 1,279 entries).
- The DPI's own disclaimer says its licences are self-reported and categorised on a best-effort basis, so "agreement with DPI" is the metric, not "accuracy against truth".

**Building the key** (`eval/build_key.py`):
1. Map DPI licence names to SPDX with `eval/dpi_licence_map.csv` (Phase 4: it lives with the eval, not the package; 52 names) (DPI's `license_paraphrases.json` plus hand mappings, each row reviewed). Terms that are not licences (`OpenAI` ToS, `Custom`, `Various`, `Non Commercial`, `Academic Research Purposes Only`) map to `non-SPDX`, and `Unspecified` / `No License` map to `none`.
2. Keep one key row per HF repo only when every DPI entry for that repo has the same expert licence set. Report how many repos this drops.
3. Expected status: card at audit time (`HF Yaml License`) vs expert set: equal -> `consistent`; both present and different -> `inconsistent`; YAML empty -> `missing`; expert `non-SPDX`/`none` -> excluded from Q3, counted separately.
4. Split by HF repo id hash: 30% dev (build tables, set the ScanCode threshold), 70% test. Freeze the config with a git tag before the test run.

**Two scanner configurations, reported separately.** Every question below is run twice on the same key, the same dev/test split and the same frozen config, changing only the scanner (`--scanner builtin` / `--scanner scancode`; never `auto` in the evaluation):
- `builtin`: the plain install's built-in SPDX matcher (§4, Phase 3), with its Dice/containment thresholds tunable on the dev split only;
- `scancode`: the `[scan]` extra, with the score threshold tuned on the dev split.

Each configuration gets its own confusion matrix, agreement with Wilson interval, kappa, abstention rate and `inconsistent` precision/recall. They are never pooled or averaged. Both runs record the tool version, ScanCode and licence-DB version (or "not installed"), and whether an HF or GitHub token was present. Any headline number in the README names its configuration.

**Measured questions:**
- **Q1 card parsing:** our C1 on the card *at the audit-time revision* (resolved via `/api/datasets/{id}/commits/main`, latest commit before the DPI summary's last-change date) vs `HF Yaml License`. Exact-match rate.
- **Q2 source licence detection:** our C4 for GitHub sources vs DPI `GitHub License` and vs the expert set. Agreement rate and `unknown` rate.
- **Q3 consistency status (headline):** our status vs the expected status, as a **4x4 confusion matrix** (consistent / inconsistent / missing / unknown; `unknown` is ours only), with:
  - agreement on decided rows, with a Wilson 95% interval;
  - Cohen's kappa;
  - the abstention (`unknown`) rate, reported separately so abstaining cannot inflate agreement;
  - precision and recall for `inconsistent`.
- **Disagreement audit:** the owner hand-labels 30 random disagreements as *ours wrong* / *key wrong* / *changed since audit* / *ambiguous*, and the counts are published with the matrix.
- Results go to `RESULTS.md` at the repo root (Phase 4; per-row data in `eval/results/`) in the tierview style: headline with its range, what it does and does not show, per-row data in JSON.

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
5. **Outputs:** per-dataset JSON + HTML, `RESULTS.md` (repo root) (counts of each status per check, with ranges where it is a rate), and a CSV. No dataset is called good or bad. The table is facts with links, and maintainers get a short note on how to re-check after fixing.

**Phase 4, as run** (details and numbers in RESULTS.md §2):
- Tier B limits from the measured budget: full scan up to **100 MB**, else a seeded **10,000-row** sample with at most **100 MB** downloaded (seed 0). A first try at 200 MB measured about 4 MB/s on this laptop, over 4 hours for the list.
- `--shard I/N` runs N processes on disjoint parts of the list; `--max N` makes rounds, with the owner's usage checked between rounds; `--retry-failed` re-runs failures once.
- The config hash includes the git tree ids of `src/`, `launch/run.py`, `launch/state.py` and `pyproject.toml`; the runner refuses uncommitted changes there and prints the commit. Tier A ran before this (hash of settings and version only).
- State is one row per (dataset, tier), not per check.
- `launch/check_listing_cap.py` flags repos whose Hub listing stops at 100,000 files (§12); `launch/summarize.py` reports every share with and without them.
- **Phase 4.5 rescan** (`launch/rescan_set.py`, `run.py --only`): after the fixes, only the rows the fixes can change are run again under the new config hash (a listing cut off at 100,000 entries, the three bugs, the old "corrupt" check); every other row keeps its first-scan hash. `summarize.py` marks which rows were rescanned, and the first scan's own summary is kept in `launch/results/first-scan/`. As run: 99 Tier B and 8 Tier A rows (the 8 with false missing-file results). 128 more Tier A datasets had a cut-off list but no missing-file result and were not rescanned (owner's scope); only a licence file beyond the cut-off could change them.
- **Zero-row samples** (Phase 4.5): 37 launch samples stopped at the 100 MB download cap before reading a row. RESULTS gives shares over datasets with at least one row read.
- No HTML per dataset yet (Phase 5 renderer).

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
| 2.12 | JSON + terminal report; CLI `check` | `report/json_out.py`, `report/terminal.py`, `cli.py` | `datasetvet check hf:stanfordnlp/imdb` runs end to end on the laptop; scan time and throughput logged to BUILD_LOG |
| 2.13 | CI: lint, type check, tests on Windows + Ubuntu, Python 3.11/3.12/3.13 | `.github/workflows/ci.yml` | green on a branch (pushed only with the owner's OK) |

### Phase 3: licence + provenance (Opus 5.5, high) — done 2026-11-19

Owner decisions taken at the start of Phase 3 (from the Phase 2 open questions): a built-in matcher in the plain install (3.9), chunked sampling (3.10), footer reworded (3.11). What was built, measured and left open is in BUILD_LOG.md.

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
| 3.9 | Built-in SPDX matcher in the plain install (owner decision) | `licences/matcher.py`, `data/spdx_licences.json.gz`, `tools/vendor_spdx.py`, `tests/test_matcher.py` | every vendored text identifies itself; close relatives told apart; notices and URLs; no AI, stdlib only |
| 3.10 | Sampling: many small chunks spread across each file (owner decision) | `checks/health/scan.py`, `tests/test_scan.py` | exact, deterministic, spread across a sorted file; label warning kept |
| 3.11 | Footer reworded; banned-words test for the footer and terminal reports | `model.py`, `tests/test_wording.py` | test passes |

### Phase 4: accuracy evaluation + launch scan (Opus 5.5, high) — done 2026-11-21

| # | task | files | done when |
|---|---|---|---|
| 4.1 | Launch budget: freeze top-500 list, sum sizes, propose the Tier B limit | `launch/freeze_list.py`, `launch/lists/` | list saved; total bytes and request estimate written to BUILD_LOG |
| 4.2 | Resumable runner with SQLite state, batching, limiter, Ctrl-C safety | `launch/run.py`, `launch/state.py`, tests | killing the process mid-batch and resuming finishes with no duplicate or missing rows (test) |
| 4.3 | DPI key builder (pinned sha), licence-name map, dev/test split | `eval/build_key.py`, `data/dpi_licence_map.csv` | key stats match §8 counts; dropped-repo count reported |
| 4.4 | Audit-time card revision lookup | `eval/revisions.py` | for 20 dev repos the chosen commit predates the DPI file date (test) |
| 4.5 | Dev run of both configurations (`builtin`, `scancode`); tune only each scanner's thresholds, then freeze config (git tag `eval-config-v1`) | `eval/run.py`, `eval/config.yml` | tag exists before any test-split result is computed |
| 4.6 | Test run of both configurations + metrics: confusion matrix, Wilson CI, kappa, abstention, inconsistent P/R, **one set per configuration** | `eval/metrics.py`, `eval/results/` | `RESULTS.md` has separate `builtin` and `scancode` sections, never pooled; owner labels 30 disagreements per configuration that has them (**samples written, labels pending**) |
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
| 5.9 | **Large-repo warning** (owner's decision, Phase 4.5): before scanning a repo with 100,000 or more files, say so before any data is read: the file count, the estimated time (from the measured rates in RESULTS.md section 4: listing time grows with the file count, the read depends on the files) and a suggestion to run a sampled scan (`--max-scan-bytes`, `--sample-rows`). Ask for confirmation in a terminal; do not wait in the GitHub Action or with `--yes`; always say it in the report's scan line | `cli.py`, `pipeline.py`, `hubs/huggingface.py` | a test with a simulated 100,000+ file list shows the warning with the count before any data file is fetched; `--yes` and a non-interactive run proceed and still print it; the README states the measured time for very large repos |

## 12. Risks and open questions

- **Name** (§1): decided, `datasetvet`. Claim the PyPI name with the first release (task 5.8), since names are first come, first served.
- **ScanCode on Windows**: long paths. Mitigated by the optional extra and docs; CI proves it (3.8).
- **The DPI key is a snapshot of self-reported, best-effort labels** (their own disclaimer). We publish agreement, not accuracy, plus the disagreement audit.
- **Dataset Viewer limits are undocumented**: measured during 4.1/4.7.
- **Launch-scan bandwidth**: unknown until 4.1 sums the sizes; Tier B's limit is set from that, not guessed.
- **PII regexes** will have false positives and misses; the output says "pattern matches", and 2.11's fixtures measure precision on known non-PII strings. No recall claim is made.
- **Licence properties**: SPDX data carries no NC/SA properties for non-CC licences, so those show none. This is narrower than the brief's wording; owner to confirm.
- ~~Footer vs banned words~~: resolved in Phase 3 (footer reworded, §7).
- ~~Default install has no text scanner~~: resolved in Phase 3 (built-in matcher, §4). §8 measures `builtin` and `scancode` separately.
- **SPDX licence list data's own licence is still not stated** (re-checked 2026-11-19: GitHub's `license` field for `spdx/license-list-data` is empty; README, CONTRIBUTING and accessingLicenses.md say nothing; the spdx.org footer says "All Rights Reserved"). ~~Owner to decide whether to keep vendoring the texts~~: **decided in Phase 4: texts are not shipped**, only metadata and a derived fingerprint index (§4). A question to SPDX is drafted in `docs/drafts/spdx-license-list-data-issue.md` for the owner to post. Still open: the metadata (ids, names, flags, URLs) is shipped and comes from the same unlicensed source.
- **Anonymous GitHub sources** can only say "no file under these 7 names", so a repo without one is `unknown`, not `missing`, unless `GITHUB_TOKEN` is set.
- **A source repo's LICENSE often covers code, not data** (hotpot_qa: card CC-BY-SA-4.0, repo Apache-2.0). The report states the two licences and that they differ, which is the fact; it does not say which one covers the data. Phase 4's disagreement audit should count how often this is the reason.
- **Built-in matcher coverage**: no non-SPDX licences, no paraphrases. Phase 4 measured it: 25.3% abstention against ScanCode's 28.6%, agreement 76.0% vs 74.9% (RESULTS §1).
- ~~**Hub file listings stop at 100,000 entries**~~ (found in Phase 4; **fixed in Phase 4.5**, §5.5 "File list"). The HF adapter took the file list from `siblings`, so for larger repos data health read a partial list (a "Full scan" label could be wrong) and card `data_files` paths were reported as missing files when they existed. 69 of 169 launch datasets checked were affected. The adapter now pages through the tree API, and says "Partial" when it cannot.
- ~~**"corrupt" overstates "could not read"**~~ (Phase 4; **fixed in Phase 4.5**, §5.5): the check is now "Files that could not be read as rows" with a kind per file, and non-data files are skipped.
- ~~**Bugs found by the launch scan**~~ (Phase 4; **fixed in Phase 4.5**, each with a test written first): nanosecond timestamps (`ValueError`), `ArrowIndexError` (pyarrow's JSON reader builds an invalid array; 2 datasets), JSON arrays of non-objects (`AttributeError`).
- ~~**Old licence texts in git history**~~ (decided and done in Phase 4.5): Phase 3's `data/spdx_licences.json.gz` (blob `deda55b`, commit `3a6b650`, now `8a92854`) held the 92 full licence texts. They came from SPDX's `license-list-data` repo, which declares no licence of its own (GitHub shows `license: null`; an issue about it is drafted in `docs/drafts/`). Whether that copy may be redistributed is unclear, so the project ships only the derived fingerprint index (no readable text, rebuilt from the official source). Leaving the texts in history would undo that on the first push, so the owner had them removed from all history with `git filter-repo` before any push. The old to new commit ids are in BUILD_LOG.
