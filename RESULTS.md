# datasetvet: Phase 4 results

Measured 2026-11-19 on the owner's Windows 11 laptop (Python 3.12.10), datasetvet 0.0.0, SPDX licence list 3.29.0, ScanCode toolkit 32.5.0. Every Hugging Face call was **anonymous**: no HF token was visible to `huggingface_hub` during these runs, and no `GITHUB_TOKEN` was set. Facts only, not legal advice.

## Headline

| | built-in matcher | ScanCode (`[scan]` extra) |
|---|---|---|
| Agreement with the DPI answer key, decided rows (test split) | **76.0%** (139 of 183; 95% CI 69.3–81.6%) | **74.9%** (131 of 175; 95% CI 67.9–80.7%) |
| Abstention (`unknown`) | 25.3% (62 of 245) | 28.6% (70 of 245) |
| Agreement counting abstentions as misses | 56.7% (139 of 245; 50.5–62.8%) | 53.5% (131 of 245; 47.2–59.6%) |
| Cohen's kappa, decided rows | 0.53 | 0.52 |
| `inconsistent`: precision / recall | 37% (16/43) / 28% (16/57) | 34% (15/44) / 26% (15/57) |

**Launch scan, top 500 HF datasets by 30-day downloads** (list frozen 2026-11-19; built-in matcher; anonymous):

| | result |
|---|---|
| Tier A (card, licence, provenance, links): checked | 499 of 500 (1 pinned revision no longer exists) |
| Card states a licence | **59.9%** (299 of 499; 95% CI 55.6–64.1%) |
| Of those, at least one comparison `inconsistent` | **12.4%** (37 of 299; 9.1–16.6%) |
| Tier B (data health): data read | 392 of 500 (195 full scans, 197 samples); 102 `not checked`, 6 failed |
| Exact duplicate rows within a split found | **18.9%** of the 392 (74; 15.3–23.0%); a lower bound for samples |
| Same input in two splits (leakage) found | **6.1%** (24 of 392; 4.1–8.9%) |

Each dataset gets facts, not a grade. The Tier B shares include 64 datasets whose file list the Hub cut at 100,000 entries (section 2, "Cut-off file lists"); without them the duplicate share is 14.9% and the leakage share 5.8%.

"Agreement" is agreement with the Data Provenance Initiative's hand-audited labels, not accuracy against a ground truth: the DPI calls its own labels self-reported and best-effort. The two scanners are reported separately and never pooled.

---

## 1. Accuracy evaluation

### Method

- **Answer key** (`eval/build_key.py`, `eval/key/`): the DPI's `data_summaries/*.json` at commit `ce6662d` of `Data-Provenance-Initiative/Data-Provenance-Collection` (Apache-2.0). 109 files, 3,718 entries, 3,492 linked to 792 unique HF repos. 81 repos were dropped because their DPI entries disagree on the expert licence set, and 3 because they have no recorded card licence, leaving 708 key rows. DPI licence names were mapped to SPDX by hand (`eval/dpi_licence_map.csv`, 52 names).
- **Expected status**: the card's licence as the DPI recorded it at audit time (`HF Yaml License`) compared with the expert licence set. `missing` if the card stated none, `consistent` if the two are equivalent SPDX expressions, `inconsistent` otherwise. Excluded: 212 rows whose expert set is "none stated" and 125 whose expert licence is not on the SPDX list (OpenAI terms, "Non Commercial", Llama, ...). That leaves **371 rows: 239 consistent, 80 inconsistent, 52 missing.**
- **Card text as it was at audit time** (`eval/revisions.py`): for each repo, the latest commit on `main` at or before the last change to its DPI summary file (May–October 2024). datasetvet then checks `hf:<id>@<that sha>`: the card's YAML licence against the README text, the repo's licence files and the stated sources. Links, data health and provenance are off. GitHub sources are read at today's HEAD; they cannot be pinned to the audit date.
- **One status per dataset** (fixed in `eval/config.yml` before any run): card states no licence → `missing`; else any comparison `inconsistent` → `inconsistent`; else any `consistent` → `consistent`; else `unknown`.
- **Split and freeze**: by hash of the repo id, 30% dev (118 rows) and 70% test (253 rows). Only each scanner's thresholds were tuned, on dev only, by the pre-stated rule "most rows agreeing; abstaining counts as not agreeing; ties go to the Phase 3 default".
  - Built-in: all 8 grid points (Dice 0.80–0.95 × containment 0.90/0.95) gave the same 79 of 116 dev rows, so it stays at 0.90 / 0.95.
  - ScanCode: score ≥ 50 gave 76 (≥ 90 gave 66; ≥ 100 gave 60), so the threshold moved from 90 to **50**.
  - The config was then committed and tagged `eval-config-v1` (`5254aab`). `eval/run.py` refuses the test split unless `eval/config.yml`, `eval/run.py` and `src/` match the tag.
- **Same inputs for both scanners**: both configurations of a row run in one process and share one HTTP memo, so they read identical bytes, GitHub included. The run used the ScanCode venv.
- **Code version.** The eval ran on the code tagged `eval-config-v1` (`5254aab`). The faster fetching added later (`a3f5428`, used by the launch scan) does not affect it: the eval turns data health off (`check_data: false`), and the new fetch routes are only reached through the data-health scan. The only change that does touch eval requests is the request spacing in `http.py`, which changes timing, not content. Re-running the test split must be done from the tag: `eval/run.py` refuses it when `src/` differs from `eval-config-v1`, as it now does on later commits.

### Test split: confusion matrices (rows: expected; columns: ours)

8 of 253 rows are excluded from both, because the repo's commit history is no longer readable anonymously (HTTP 401: now gated or removed). 245 rows are scored.

**built-in matcher** (dice ≥ 0.90, containment ≥ 0.95)

| expected \ ours | consistent | inconsistent | missing | unknown | total |
|---|---|---|---|---|---|
| consistent | **99** | 27 | 7 | 29 | 162 |
| inconsistent | 10 | **16** | 0 | 31 | 57 |
| missing | 0 | 0 | **24** | 2 | 26 |

**ScanCode** (score ≥ 50)

| expected \ ours | consistent | inconsistent | missing | unknown | total |
|---|---|---|---|---|---|
| consistent | **92** | 29 | 7 | 34 | 162 |
| inconsistent | 8 | **15** | 0 | 34 | 57 |
| missing | 0 | 0 | **24** | 2 | 26 |

Per-row data: `eval/results/runs/test.jsonl`. All metrics: `eval/results/metrics-test.json`.

### Other measured questions

- **Q1, card parsing at the audit-time revision.** Our card licence (C1) matched the DPI's recorded value in **225 of 245 rows (91.8%; 87.7–94.7%)**. The 20 mismatches are mostly about how the value was recorded, not which revision was read:
  - the DPI kept one value from a multi-licence list (`[cc-by-sa-3.0, gpl-3.0]` recorded as CC BY-SA 3.0);
  - the DPI recorded a specific licence for HF family ids (`gpl` as GPL v3, `bsd` as BSD-3-Clause, `cc` as CC0);
  - 7 `bigbio/*` and other cards have no `license` key at the chosen revision but the DPI recorded one.
  - These 7 are the "expected consistent → ours `missing`" cell.
- **Q2, source licences.** For the 45 test rows where we read a GitHub source and the DPI recorded a GitHub licence, our detection agreed in **45 of 45** (both scanners; 95% CI 92.1–100%).
- **What drives our `inconsistent`** (built-in; a row can count twice):
  - 33 from a GitHub source's LICENSE;
  - 14 from the README text.
  - A source repo's LICENSE often covers its code, not the data. datasetvet states both licences and that they differ; the DPI's expert set records one licence for the dataset. This is the main reason for the 27 "expected consistent → ours `inconsistent`" rows.
- **Post-hoc, exploratory, not a headline.** This was chosen after seeing the test results, so it is not part of the frozen config. Using only the dataset's own repo (README text and repo licence files) and ignoring stated sources:
  - built-in: 85.6% agreement on decided rows (137/160; 79.4–90.2%), 34.7% abstention, kappa 0.67;
  - ScanCode: 84.4% (119/141; 77.5–89.5%), 42.4% abstention, kappa 0.67;
  - `inconsistent` recall falls to 9/57 and 8/57.
  - So the choice is a trade-off, not a free gain.
- **Dev split** (for reference, tuned on): built-in 79/116 rows agreeing (87.8% of 90 decided); ScanCode ≥ 50 76/116 (86.4% of 88 decided).

### Disagreement audit (pending the owner)

`eval/results/disagreements-builtin.csv` and `disagreements-scancode.csv` hold 30 randomly chosen disagreements each (seed 4), with an empty column for the owner's label (*ours wrong / key wrong / changed since audit / ambiguous*). They are not labelled yet, so no breakdown is published.

### What this shows and does not show

- It shows how often datasetvet's licence status matches a large human audit when both read the same card. The built-in matcher is at least as close to that audit as ScanCode on this key (the intervals overlap), with fewer abstentions. So skipping the 774 MB extra costs nothing measurable here.
- It does not show correctness: the key is one team's best-effort labels from 2024. It also has a different target. The DPI decides "the dataset's licence"; datasetvet reports whether each piece of evidence agrees with the card. Low `inconsistent` precision is largely this difference, not misreading.
- It covers only datasets in the DPI collection (instruction and fine-tuning text data, mostly 2021–2024 cards), with expert licences on the SPDX list.

---

## 2. Launch scan: top 500 Hugging Face datasets

**Code.** Tier B (data health) ran on commit `a3f5428` ("Faster data fetching"), config hash `2472d09329f26eb6`. The hash includes the git tree ids of `src/`, `launch/run.py`, `launch/state.py` and `pyproject.toml`, and `launch/run.py` refuses to run with uncommitted changes there, so every finished row names the committed code that made it. Before that commit, the fetch routes were checked against the one-file-at-a-time route on 40 Tier B datasets (`launch/fetch_equivalence.py`). 39 reports were identical field by field, excluding timings and request counts. The 40th differed only in the Parquet-conversion commit, which Hugging Face rebuilt on 2026-11-20; the old route showed the same change. Every request still obeys the Hub's RateLimit headers and waits out 429s.

**Tier A** ran on 2026-11-19 at `5254aab`, before the config hash named the code (config hash `d0b085a50bef68aa`, settings and version only). Its checks (card, licence, provenance, links) are unchanged in `a3f5428`: that commit changed data fetching, the CDN spacing in `http.py` (timing only) and a git-fetch plan in the HF adapter that only data health reads.

### Method

- **List** (`launch/freeze_list.py`, `launch/lists/top500-2026-11-19.json`): the 500 most-downloaded datasets by the Hub's 30-day count on 2026-11-19 at 21:11 (+04:00), each pinned to its commit sha. No private or disabled repo was met. Sizes came from the Dataset Viewer `/size` for 251 of them (291 TB of Parquet together); the rest gave an error or no conversion. 829 requests, 23 minutes.
- **Every check reads `hf:<id>@<frozen sha>`**, anonymously, through one rate-limited HTTP client per process. It obeys the Hub's `RateLimit` headers (pauses below 20% of the window) and waits out every 429.
- **Tier A** (all 500): card fields, licence consistency (built-in matcher), provenance to depth 2, links. No data is downloaded. 2,921 HTTP requests, 2,937 s of checking (one process).
- **Tier B** (all 500): data health only, with launch limits chosen from the measured budget, not the tool's defaults:
  - full scan when a dataset's data is ≤ 100 MB;
  - otherwise a seeded sample of 10,000 rows (seed 0) in small chunks across each file read, with at most 100 MB downloaded;
  - 3 parallel processes (`--shard I/3`), in 3 rounds of up to 60 datasets each, then one retry of the failures. Usage was checked between rounds.
  - Wall clock 2026-11-20 14:34 to 2026-11-21 06:35 (+04:00), about 16 hours; 75,801 s of checking across the 3 processes; 602,535 HTTP requests. No 429 was received.
- **State** (`launch/state.sqlite`): one row per dataset and tier, holding the report, the config hash and the time. `launch/summarize.py` writes `launch/results/datasets.csv` (one row per dataset, facts only) and `launch/results/summary.json`. Each tier's rows all carry one config hash (checked in `summary.json`).

### Tier A: cards, licences, provenance, links

| | count |
|---|---|
| Checked | 499 of 500. `KakologArchives/KakologArchives`: its frozen sha now returns HTTP 404 |
| Gated | 31 (27 automatic, 4 manual approval). The card metadata from the API and the links are checked; the README text and the files are not readable anonymously |
| Card licence `present` | 299 (59.9%; 55.6–64.1%) |
| Card licence `missing` | 200 (40.1%) |

**Licence comparisons** (card licence vs README text, licence files and stated sources; four statuses only):

| for the 299 cards with a licence | datasets | share (95% CI) |
|---|---|---|
| at least one comparison `inconsistent` | 37 | 12.4% (9.1–16.6%) |
| at least one `consistent`, none `inconsistent` | 109 | 36.5% (31.2–42.1%) |
| only `missing` or `unknown` (nothing else stated a licence we could identify) | 153 | 51.2% (45.5–56.8%) |

All comparisons together: 214 `consistent`, 62 `inconsistent`, 289 `missing`, 289 `unknown`. The accuracy evaluation (section 1) applies: an `inconsistent` often means a source repo's LICENSE (for its code) differs from the card's data licence, and datasetvet states that difference, not which licence covers the data.

**Provenance:** 11 datasets declare parents (`source_datasets`), giving 14 comparisons: 2 `inconsistent`, 4 `missing`, 8 `unknown`.
- `EleutherAI/lambada_openai`: card MIT, parent `cimec/lambada` CC-BY-4.0.
- `jat-project/jat-dataset`: card Apache-2.0, parent `oscar-corpus/oscar` CC0-1.0.

**Links:** 1,156 checked in 168 datasets: 402 `ok`, 731 `dead`, 11 `restricted`, 7 `unreachable`, 5 `unknown`.
- 716 of the 731 `dead` are card `configs[].data_files` paths that match no file in the repo's listing ("missing file").
  - 550 of them are in `HuggingFaceFW/fineweb-2`. Its card declares a test split for 550 languages that have only a train file (checked: `data/abi_Latn/` holds only `train/000_00000.parquet`).
  - **157 are false:** they come from 8 repos whose file listing the Hub cut at 100,000 entries. In the 3 repos checked by hand, the paths exist.
- 15 are dead URLs in 12 datasets.
- Datasets with at least one dead link: 23 of 168 (13.7%). **Without the 157 false results: 15 of 168 (8.9%; 5.5–14.2%).**

### Tier B: data health

| | datasets |
|---|---|
| Data read | 392: 195 full scans, 197 samples (135 of them stopped at the 100 MB download cap) |
| Read from | 230 HF's Parquet conversion, 162 the original files |
| `not checked` | 102: 58 no Parquet conversion and no Parquet/CSV/JSON Lines files; 30 gated (26 automatic, 4 manual); 14 Dataset Viewer turned off by the owner and no `configs` in the card |
| Failed | 6, listed below |
| Read in total | 12.3 GB, 13,181,583 rows |

**Findings** (a dataset counts once per check; "found" is a fact about the rows read):

| check | found in | share (95% CI) | without the 64 cut-off listings |
|---|---|---|---|
| exact duplicate rows within a split | 74 of 392 | 18.9% (15.3–23.0%) | 49 of 328, 14.9% (11.5–19.2%) |
| same input in two splits (leakage) | 24 of 392 | 6.1% (4.1–8.9%) | 19 of 328, 5.8% (3.7–8.9%) |
| empty rows | 13 of 392 | 3.3% (1.9–5.6%) | 10 of 328, 3.0% (1.7–5.5%) |
| PII pattern matches (email, phone) | 61 of 253 with string columns | 24.1% (19.3–29.7%) | 52 of 213, 24.4% (19.1–30.6%) |
| a file could not be read | 47 of 392 | 12.0% (9.1–15.6%) | 30 of 328, 9.1% (6.5–12.8%) |

- **Samples count less.** In a sample, duplicate and leakage counts are lower bounds ("at least"). Full scans: duplicates in 39 of 195 (20.0%); samples: 35 of 197 (17.8%).
- **PII** means pattern matches, not personal data.
- **"Could not be read" is mostly our reader, not broken data.** All 47 are original-file scans; 0 of the 230 Parquet-conversion scans had one.
  - 38: a `.json` file that is not a table of rows (for example a tokenizer or config file in the data folder), which Arrow cannot parse as rows.
  - 8: a datasetvet bug: a JSON array whose items are not objects raises `AttributeError`.
  - 1: HTTP 404 for a file the Hub lists at that revision.
  - The report calls this check "corrupt"; that wording overstates it (section 3).

**Failed (6):**
- 3 `DatasetNotFound`: `defeatbeta/yahoo-finance-data` and `HubLabs/HubEgo-100K` were deleted or made private after the list was frozen; `KakologArchives/KakologArchives`'s frozen sha is gone.
- 2 `ArrowIndexError`: `Yshh525/rho-internalize-v1-20261021` and `neurodeskorg/webapps`. A datasetvet bug, not yet diagnosed.
- 1 `ValueError`: `trentmkelly/polymarket_historical_data`. A datasetvet bug: a nanosecond timestamp that does not fit a Python `datetime` stops the scan.
- `i998979/TransitApp` failed once with a Windows file error (`WinError 1392`) on a temp file. It passed on the retry and is counted as done.

**Fetch routes** (`a3f5428`):
- The git pack served 49,975 files for 22 datasets. 301,441 files came over HTTP, up to 8 at a time.
- Four repos took 44,718 s, 59% of all checking time: `nvidia/PhysicalAI-WorldModel-Synthetic-Autonomous-Driving-Scenarios` 4.2 h, `lyzenghq/banned-historical-archives` 3.6 h, `AquaV/genshin-voices-separated` 2.8 h, `TGMR/one_pass_ingestion` 1.9 h. Each has over 100,000 files, mostly a few hundred bytes each.
  - Their listings are cut off (below), so the git route was not used, by design.
  - Their samples were spread over thousands of files of a few hundred bytes each, one HTTP request per file.

### Cut-off file lists (found during this scan)

The Hub's dataset API returns at most 100,000 entries in `siblings`, and datasetvet (at `a3f5428` and before) takes a repo's file list from there. `launch/check_listing_cap.py` re-read the listing at each frozen sha for every Tier A dataset with a missing-file result and every Tier B dataset read from original files (169 datasets). 69 have exactly 100,000 entries (`launch/results/listing-truncated.json`):
- **Tier A:** 8 of them gave the 157 false missing-file results above.
- **Tier B:** 64 of the 162 original-file scans read from a partial file list. 18 of them are labelled "Full scan" but read only the files in that list. The 46 samples drew from part of the repo.
- Parquet-conversion scans and card and licence reading are not affected; licence files beyond the cut-off would be missed, but no case was checked.

The fix is to page through the Hub's tree API when `siblings` has 100,000 entries. It is not in this run: changing the code would change the config hash and re-run all 500.

---

## 3. Limits

- **Anonymous runs.** No HF token was visible to `huggingface_hub` (no `HF_TOKEN`, nothing at `C:\Users\melsa\.cache\huggingface\token`), so gated cards and gated data are not readable. 8 eval rows were excluded for that reason. With a token, the HF API allowance doubles.
- **GitHub, anonymous.** Only the 9 standard licence file names are tried at HEAD. A repo without one is `unknown`, not `missing`.
- **Answer-key drift.** The key is a 2024 snapshot. Q1/Q3 use audit-time card revisions, but GitHub sources are read today.
- **Scanner coverage.** The built-in matcher knows only SPDX-listed licences and exact names. Non-SPDX terms and paraphrases ("research use only") give `unknown`.
- **Disagreement audit not done.** The 30-row samples await the owner's labels.

- **Launch scan, anonymous.** The README text of 31 gated datasets and the data of 30 were not read; with a token and accepted terms they could be.
- **Launch limits, not defaults.** Tier B's 100 MB / 10,000 rows / 100 MB cap were chosen to fit one laptop in about a day. A default `datasetvet check` scans up to 5 GB in full, so its counts would be higher for the 197 sampled datasets.
- **Cut-off listings.** 64 Tier B scans and 8 Tier A link checks used a file list cut at 100,000 entries (section 2). Shares are given with and without them.
- **"Corrupt" means "could not read".** 46 of the 47 are JSON files that are not row tables or a datasetvet bug. The check's name and wording need to change before launch.
- **Three datasetvet bugs found by the scan** (6 datasets): nanosecond timestamps (1), `ArrowIndexError` (2), JSON arrays of non-objects (8 datasets with a file counted as "could not be read"). They are not fixed in this run.
- **Snapshot.** Each result is for the frozen sha. The Hub changes daily: 3 of the 500 were gone within two days.
- **Tier A code.** Tier A ran on `5254aab` with the earlier config-hash method (settings and version, not code trees).
