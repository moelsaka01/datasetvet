# datasetvet: results (accuracy evaluation Phase 4, launch scan updated in Phase 4.5, ScanCode threshold check Phase 5, v2 rules Phase 5.5)

> **Phase 5.5 (2026-11-22): v2 licence rules are built and frozen (`eval-config-v2`), and the held-out evaluation waits for the owner's blind labels.** No held-out number exists yet, and none is given below. The headline table further down is **v1** (the Phase 4 rules). Section 0 has what v2 does on the rows it was tuned on and on the old test split, which is **no longer blind**.

## 0. Phase 5.5: v2 rules (held-out score pending)

**Pre-registered** before any rule work (PLAN.md §8.1, commit `ed0ad4d`). On a fresh held-out set, v2 (built-in matcher) must reach: Cohen's kappa ≥ 0.61 on decided rows; abstention < 15%; and more agreeing rows than baseline A (the HF `license:` tag alone) and baseline B (ScanCode alone), with an exact McNemar p < 0.05 for each.

**Held-out set:** 120 datasets drawn with `random.Random(20261122)` from the 492 launch-list datasets that are neither in the DPI collection (7 were) nor gone (1). The labelling sheet shows no datasetvet output. It was committed and tagged `holdout-v1` (`eb8bfad`) before any label existed. The rules, the runners, both baselines and the scorer were then frozen as `eval-config-v2` (`45122c5`). **Labels: not yet given.** Next steps: the owner labels `eval/holdout/sheet.csv` blind (instructions in `eval/holdout/LABELLING.md`), then `eval/holdout/predict.py` and `eval/holdout/score.py` produce the tables. Both refuse to run off the tag or on an incomplete sheet.

From the sheet alone (card fields, not datasetvet output): 76 of the 120 cards state a YAML licence, 24 repos have no README at the frozen sha, and 1 (`defeatbeta/yahoo-finance-data`) was deleted after the list was frozen, so it cannot be scored. Under the DPI rules, cards with no licence where nothing else states one, and non-SPDX cards, are excluded. So fewer than 120 rows will be scored. If fewer than 60 remain, a second batch of 60 is drawn (seed 20261123) before anything is scored.

### What changed in v2 (rules only, no AI)

Tuned only on the dev split (118 rows) and the 48 datasets of the two Phase 4 disagreement samples. Those samples still have no owner labels, so the DPI key's labels were used. Details in PLAN.md §5.2 "Phase 5.5".

1. **"The source code licence differs."** A stated source repo's licence file naming only OSI-approved licences, against a card naming a data licence (not OSI-approved), is `unknown` with that fact, not `inconsistent`. Example: hotpot_qa's card says CC-BY-SA-4.0, and `github.com/hotpotqa/hotpot` has an Apache-2.0 LICENSE.
2. **Software licences set aside in one text.** "Code MIT, data CC-BY-4.0" in a README is `consistent` with a CC-BY-4.0 card.
3. **One status per dataset** (`licence.summary`). A card licence that no place read states or contradicts is `consistent` with the sub-fact **"uncontradicted, not confirmed"**. Before, it was `unknown`.

The OSI-approved flag of the SPDX licence list is now the one licence property that decides something (rules 1 and 2).

### On the rule-work rows (tuned on; not an accuracy claim)

164 scored rows (116 dev, and 48 from the disagreement samples: rows where v1's built-in or ScanCode run disagreed with the key, so v1 scores badly on them by construction). Rows agreeing with the key, abstaining counted as a miss (`eval/results/metrics-rulework-v2.json`):

| rules | agree | abstention | kappa, decided rows |
|---|---|---|---|
| v1 | 84 of 164 | 29.3% | 0.50 |
| + uncontradicted | 109 | 7.3% | 0.42 |
| + code licence (data-licence card) | 92 | 31.7% | 0.62 |
| + code licence (any card) | 91 | 31.7% | 0.60 |
| all three, data-licence card (**frozen**) | **119** | **7.3%** | **0.50** |
| all three, any card | 118 | 7.3% | 0.48 |
| all but the set-aside rule | 117 | 8.5% | 0.50 |

Each rule passes the pre-stated test: it raises the number of agreeing rows. Kappa does not improve. The code-licence rule raises it, and the uncontradicted rule lowers it, because some cards the expert marked `inconsistent` state a licence that nothing else contradicts.

### On the old test split (no longer blind)

**Not blind.** These 245 rows were scored in Phase 4, looked at again in Phase 5, and 48 of their datasets were used in this rule work. Same rows and the same audit-time card revisions as v1; frozen v2 code (`eval/results/runs/test-v2.jsonl`, `eval/results/metrics-test-v2.json`). Baseline A here is the card's YAML licence at the audit revision (no licence → `missing`, any licence → `consistent`). It is for context and was not pre-registered for this split.

| | v1 (Phase 4) | **v2** | A: tag alone |
|---|---|---|---|
| rows agreeing, abstaining = miss | 139 of 245 (56.7%; 50.5–62.8%) | **177 of 245 (72.2%; 66.3–77.5%)** | 179 of 245 |
| abstention (`unknown`) | 25.3% | **6.5%** | 0% |
| agreement, decided rows | 76.0% (69.3–81.6%) | 77.3% (71.4–82.2%) | 73.1% |
| kappa, decided rows (bootstrap 95%) | 0.53 (0.40–0.64) | **0.46 (0.34–0.58)** | 0.34 (0.23–0.45) |
| `inconsistent` precision / recall | 16/43 / 16/57 | 9/17 / 9/57 | never says it |

- **v2 vs v1:** 45 rows right only with v2 and 7 only with v1 (exact McNemar p ≈ 7e-8). Fewer abstentions, at the cost of kappa.
- **v2 vs the tag alone:** 9 rows right only with v2 and 11 only with A (p = 0.82). **On this split v2 does not beat the tag alone on agreement.** It has the higher kappa, because A can never say `inconsistent`.
- **Where v2 is wrong.** 37 rows the key calls `inconsistent` get `consistent` from v2. 23 of them are "uncontradicted": nothing in the card's repo or its readable sources names another licence, and the DPI expert found one elsewhere (paper, homepage, upstream data). Rules that read only the card, the repo and GitHub cannot see that.
- **Inputs.** The cards are the same audit-time revisions. GitHub sources are read at today's HEAD for both v2 (2026-11-22) and v1 (2026-11-19), so a repo that changed in between would differ; the Phase 5 threshold check found no drift over the same period.
- **Rows not used in rule work (197).** v1 134 agree (kappa 0.70), v2 151 (kappa 0.55); abstention 20.3% → 4.6%.

Confusion matrix, v2, old test split (rows: expected; columns: v2):

| expected \ v2 | consistent | inconsistent | missing | unknown |
|---|---|---|---|---|
| consistent | **144** | 8 | 7 | 3 |
| inconsistent | 37 | **9** | 0 | 11 |
| missing | 0 | 0 | **24** | 2 |

v2 says `consistent` for 181 rows: 128 "confirmed" (another place states the same licence) and 53 "uncontradicted". Of the 53, 30 match the key and 23 do not.

**What this predicts for the held-out score, before any label exists.** If the held-out labels behave like the DPI key, the pre-registered goal is likely missed on two parts: kappa ≥ 0.61 (0.46 here) and beating the tag alone with p < 0.05 (a tie here). Abstention < 15% looks reachable. The goal stays as registered, and the held-out result will be reported as it comes out.

Measured 2026-11-19 to 2026-11-21 on the owner's Windows 11 laptop (Python 3.12.10), datasetvet 0.0.0, SPDX licence list 3.29.0, ScanCode toolkit 32.5.0. Every Hugging Face call was **anonymous**. During the first runs no HF token was visible to `huggingface_hub`. For the rescan (2026-11-21) a token existed on the laptop and was hidden on purpose (`HF_TOKEN_PATH` set to a file that does not exist), so the rescan ran under the same conditions as the first scan. The one exception is the timing of a very large repo (section 2, last part), which the owner allowed to run logged in. No `GITHUB_TOKEN` was set. Facts only, not legal advice.

## Headline

| | built-in matcher | ScanCode (`[scan]` extra) |
|---|---|---|
| Agreement with the DPI answer key, decided rows (test split) | **76.0%** (139 of 183; 95% CI 69.3–81.6%) | **74.9%** (131 of 175; 95% CI 67.9–80.7%) |
| Abstention (`unknown`) | 25.3% (62 of 245) | 28.6% (70 of 245) |
| Agreement counting abstentions as misses | 56.7% (139 of 245; 50.5–62.8%) | 53.5% (131 of 245; 47.2–59.6%) |
| Cohen's kappa, decided rows | 0.53 | 0.52 |
| `inconsistent`: precision / recall | 37% (16/43) / 28% (16/57) | 34% (15/44) / 26% (15/57) |

**Launch scan, top 500 HF datasets by 30-day downloads** (list frozen 2026-11-19; built-in matcher; anonymous; after the Phase 4.5 fixes and rescan, section 2):

| | result |
|---|---|
| Tier A (card, licence, provenance, links): checked | 499 of 500 (1 pinned revision no longer exists) |
| Card states a licence | **59.9%** (299 of 499; 95% CI 55.6–64.1%) |
| Of those, at least one comparison `inconsistent` | **12.4%** (37 of 299; 9.1–16.6%) |
| Tier B (data health): at least one row read | 356 of 500 (189 full scans, 167 samples); 38 more stopped at the launch download cap or had only unreadable files; 103 `not checked`; 3 failed (no longer on the Hub) |
| Exact duplicate rows within a split found | **20.5%** of the 356 (73; 16.6–25.0%); a lower bound for samples |
| Same input in two splits (leakage) found | **6.7%** (24 of 356; 4.6–9.8%) |

Each dataset gets facts, not a grade. 107 rows were rescanned after the fixes (99 Tier B, 8 Tier A) and are marked in `launch/results/datasets.csv` (`rescanned_A`, `rescanned_B`). Section 2 ends with what the first scan got wrong.

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
  - The config was then committed and tagged `eval-config-v1` (`1d8f4e4`). `eval/run.py` refuses the test split unless `eval/config.yml`, `eval/run.py` and `src/` match the tag.
- **Same inputs for both scanners**: both configurations of a row run in one process and share one HTTP memo, so they read identical bytes, GitHub included. The run used the ScanCode venv.
- **Code version.** The eval ran on the code tagged `eval-config-v1` (`1d8f4e4`). The faster fetching added later (`cdb210e`, used by the launch scan) does not affect it: the eval turns data health off (`check_data: false`), and the new fetch routes are only reached through the data-health scan. The only change that does touch eval requests is the request spacing in `http.py`, which changes timing, not content. Re-running the test split must be done from the tag: `eval/run.py` refuses it when `src/` differs from `eval-config-v1`, as it now does on later commits.

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

### ScanCode threshold: 50 against 90, on the test split (Phase 5)

The frozen test run scored ScanCode at 50 only. Before making 50 the code default, 90 (the Phase 3 plan) was scored on the same test rows (`eval/threshold_check.py`, 2026-11-22). **This is a second look at the test split**, made to confirm a choice that the dev split had already made, not a new tuning step; nothing else was changed after it. Both thresholds ran in one process, so they read identical bytes. The 50 row reproduces the frozen result exactly (131 of 245, the same matrix), which also shows the GitHub sources had not drifted since the first run.

| ScanCode threshold | rows agreeing, abstaining counted as a miss | abstention | agreement, decided rows | kappa | `inconsistent` precision / recall |
|---|---|---|---|---|---|
| ≥ 50 (new default) | **131 of 245** (53.5%; 47.2–59.6%) | 28.6% (70) | 74.9% (131/175; 67.9–80.7%) | 0.52 | 15/44 / 15/57 |
| ≥ 90 | 110 of 245 (44.9%; 38.8–51.2%) | 39.2% (96) | 73.8% (110/149; 66.2–80.2%) | 0.51 | 10/36 / 10/57 |

- **50 beats 90 on the pre-stated rule** (most rows agreeing; abstaining counts as a miss): +21 rows. Row by row, 22 rows agree only at 50 and 1 only at 90 (exact sign test, p ≈ 6e-6).
- **Why:** the gain is from fewer abstentions, not from a looser reading. Agreement on decided rows is about the same (74.9% against 73.8%). Of the 26 rows that 50 decides and 90 leaves `unknown`, 21 (81%) match the key.
- **Cost:** the extra decisions include wrong ones. `inconsistent` precision is 34% at 50 against 28% at 90 (counts above), so neither threshold matches the key well on that status; the main reason is a different target, not misreading (see "What drives our `inconsistent`" above).
- **Decision:** `SCANCODE_MIN_SCORE` is now 50. A report names the threshold ("detections with score >= 50"). The built-in matcher is unchanged: its 8 grid points were equal on the dev split.

### Human audit (pending the owner's labels)

`eval/results/disagreements-builtin.csv` and `disagreements-scancode.csv` hold 30 randomly chosen disagreements each (seed 4), with a column for the owner's label (*ours wrong / key wrong / changed since audit / ambiguous*). **The copies in this repository were still unlabelled when Phase 5 was prepared (2026-11-22), so no breakdown is published and none is invented.** Once the label column is filled in, `python eval/audit.py` prints this table (it refuses while any row is empty; `eval/results/audit.json` records the counts) and it replaces the placeholder below. The two scanners are counted separately.

| scanner | rows labelled | datasetvet's fault | the key's fault | changed since the audit | ambiguous |
|---|---|---|---|---|---|
| built-in matcher | 0 of 30 | not labelled | not labelled | not labelled | not labelled |
| ScanCode (≥ 50) | 0 of 30 | not labelled | not labelled | not labelled | not labelled |

### What this shows and does not show

- It shows how often datasetvet's licence status matches a large human audit when both read the same card. The built-in matcher is at least as close to that audit as ScanCode on this key (the intervals overlap), with fewer abstentions. So skipping the 774 MB extra costs nothing measurable here.
- It does not show correctness: the key is one team's best-effort labels from 2024. It also has a different target. The DPI decides "the dataset's licence"; datasetvet reports whether each piece of evidence agrees with the card. Low `inconsistent` precision is largely this difference, not misreading.
- It covers only datasets in the DPI collection (instruction and fine-tuning text data, mostly 2021–2024 cards), with expert licences on the SPDX list.

---

## 2. Launch scan: top 500 Hugging Face datasets

**Code.**
- **First scan.** Tier A ran on `1d8f4e4` (config hash `d0b085a50bef68aa`, settings and version only). Tier B ran on `cdb210e` (config hash `2472d09329f26eb6`).
- **Rescan.** The 107 affected rows were rescanned on `4085159`: Tier A under config hash `7c024a7a384b9026`, Tier B under `fe7d94fb698d5f41`.
- **What the config hash covers.** Since `bc89e12` it includes the git tree ids of `src/`, `launch/run.py`, `launch/state.py` and `pyproject.toml`. `launch/run.py` refuses to run with uncommitted changes there, so every finished row names the committed code that made it.
- **Rows not rescanned** keep their first-scan result and hash. Nothing they depend on changed: Parquet-conversion scans, cards, licence comparisons and link checks of repos with complete file lists.
- **Faster fetching** (`cdb210e`) was checked against the one-file-at-a-time route on 40 Tier B datasets (`launch/fetch_equivalence.py`). 39 reports were identical field by field, excluding timings and request counts. The 40th differed only in its Parquet-conversion commit, which Hugging Face rebuilt on 2026-11-20; the old route showed the same change.
- Every request obeys the Hub's RateLimit headers and waits out 429s.

### Method

- **List** (`launch/freeze_list.py`, `launch/lists/top500-2026-11-19.json`): the 500 most-downloaded datasets by the Hub's 30-day count on 2026-11-19 at 21:11 (+04:00), each pinned to its commit sha. No private or disabled repo was met. Sizes came from the Dataset Viewer `/size` for 251 of them (291 TB of Parquet together); the rest gave an error or no conversion. 829 requests, 23 minutes.
- **Every check reads `hf:<id>@<frozen sha>`**, anonymously, through one rate-limited HTTP client per process. It obeys the Hub's `RateLimit` headers (pauses below 20% of the window) and waits out every 429.
- **Tier A** (all 500): card fields, licence consistency (built-in matcher), provenance to depth 2, links. No data is downloaded.
- **Tier B** (all 500): data health only, with launch limits chosen from the measured budget, not the tool's defaults:
  - full scan when a dataset's data is ≤ 100 MB;
  - otherwise a seeded sample of 10,000 rows (seed 0) in small chunks across each file read, with at most 100 MB downloaded.
- **First scan.**
  - Tier A: 2026-11-19, one process, 2,921 requests, 2,937 s.
  - Tier B: 2026-11-20 14:34 to 2026-11-21 06:35 (+04:00). 3 parallel processes (`--shard I/3`) in 3 rounds of up to 60 datasets each, with the owner's plan usage checked between rounds, then one retry of the failures. 75,801 s of checking, 602,535 requests, no 429 received.
- **Rescan** (2026-11-21 12:58 to 22:50, +04:00):
  - Datasets chosen by `launch/rescan_set.py` (`launch/results/rescan-set.json`, with the reason for each).
  - Run with `launch/run.py --only`: Tier B in 3 shards, one batch each; Tier A in one process. Plan usage was checked before starting.
  - Tier B: 81,537 s of checking, 317,975 requests. Tier A: 7,259 s, 3,760 requests. No dataset failed and the logs show no rate-limit errors.
- **State** (`launch/state.sqlite`): one row per dataset and tier, holding the report, the config hash and the time.
  - `launch/summarize.py` writes `launch/results/datasets.csv` (one row per dataset, facts only, with `rescanned_A` / `rescanned_B`) and `launch/results/summary.json` (the config hashes behind each tier's rows).
  - The first scan's table and summary are kept in `launch/results/first-scan/`.

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

All comparisons together: 214 `consistent`, 62 `inconsistent`, 289 `missing`, 289 `unknown`. The 8 rescanned datasets' licence results did not change. The accuracy evaluation (section 1) applies: an `inconsistent` often means a source repo's LICENSE (for its code) differs from the card's data licence, and datasetvet states that difference, not which licence covers the data.

**Provenance:** 11 datasets declare parents (`source_datasets`), giving 14 comparisons: 2 `inconsistent`, 4 `missing`, 8 `unknown`.
- `EleutherAI/lambada_openai`: card MIT, parent `cimec/lambada` CC-BY-4.0.
- `jat-project/jat-dataset`: card Apache-2.0, parent `oscar-corpus/oscar` CC0-1.0.

**Links:** 1,000 checked in 166 datasets: 403 `ok`, 575 `dead`, 11 `restricted`, 6 `unreachable`, 5 `unknown`.
- 560 of the 575 `dead` are card `configs[].data_files` paths that match no file in the repo ("missing file"). 550 of them are in `HuggingFaceFW/fineweb-2`: its card declares a test split for 550 languages that have only a train file (checked: `data/abi_Latn/` holds only `train/000_00000.parquet`). The others are in `applied-ai-018/pretraining_v1-omega` (5), `lmms-lab/LLaVA-Video-178K` (4) and `McGill-NLP/WebLINX-full` (1: `chat/test_iid.csv`, checked against the tree API: the folder has `test.csv` and four `test_*.csv`, but no `test_iid.csv`).
- 15 are dead URLs in 12 datasets.
- Datasets with at least one dead link: **16 of 166 (9.6%; 6.0–15.1%)**.

### Tier B: data health

| | datasets |
|---|---|
| Data health run | 394: 190 full scans, 204 samples (135 samples stopped at the 100 MB download cap) |
| At least one row read | **356** (189 full, 167 samples). The other 38: 37 samples that stopped at the 100 MB download cap before reading a row, and 1 full scan (`stair-lab/nonmyopia_results`) whose 7,527 files could not be read as rows |
| Read from | 232 HF's Parquet conversion, 162 the original files |
| `not checked` | 103: 58 no Parquet conversion and no Parquet/CSV/JSON Lines files; 30 gated (26 automatic, 4 manual); 14 Dataset Viewer turned off by the owner and no `configs` in the card; 1 (`gradio/frontend`) whose only JSON files are front-end and package files, not data |
| Failed | 3, all `DatasetNotFound` (below) |
| Read in total | 12.5 GB, 14,021,885 rows |

**Findings** (a dataset counts once per check; "found" is a fact about the rows read; shares are over the 356 datasets with at least one row read):

| check | found in | share (95% CI) |
|---|---|---|
| exact duplicate rows within a split | 73 | 20.5% (16.6–25.0%) |
| same input in two splits (leakage) | 24 | 6.7% (4.6–9.8%) |
| empty rows | 11 | 3.1% (1.7–5.4%) |
| PII pattern matches (email, phone) | 66 of 258 with string columns | 25.6% (20.6–31.2%) |
| files that could not be read as rows | 32 | 9.0% (6.4–12.4%) |

- **Samples count less.** In a sample, duplicate and leakage counts are lower bounds ("at least"). Full scans: duplicates in 36 of 189 (19.0%), leakage in 16 (8.5%). Samples: duplicates in 37 of 167 (22.2%), leakage in 8 (4.8%).
- **PII** means pattern matches, not personal data.
- **Files that could not be read as rows** (`health.unreadable`, called `corrupt` in the first scan). It now skips files that are not data: tokenizer and config JSON, package metadata, dependency folders. Each file gets a kind. All 40 datasets with such files (32 with rows read, 8 without) read original files; none of the 232 Parquet-conversion scans had one.
  - **`reader_limit`** (24 datasets): the file is valid but has more than one type in a column, which datasetvet's reader cannot put in one table.
  - **`invalid`** (19): the content does not parse as its file type. Examples: CSV rows with extra columns, JSON with a syntax error, `.json` files that are binary (6 video-copy datasets).
  - **`empty`** (12): the file has no rows.
  - **`download`** (1): `lyzenghq/banned-historical-archives`. 59,957 of the files the Hub lists return HTTP 404 from its storage. Checked by hand for 3: the Hub's `resolve` URL redirects to `cdn.hf.co`, which returns 404.
- None of these means the data is damaged; the report says so for each file.

**Failed (3):** `defeatbeta/yahoo-finance-data` and `HubLabs/HubEgo-100K` were deleted or made private after the list was frozen; `KakologArchives/KakologArchives`'s frozen sha is gone.

**The three bug datasets now complete:**
- `trentmkelly/polymarket_historical_data`: sampled, 10,000 rows.
- `Yshh525/rho-internalize-v1-20261021`: sampled, 10,000 rows; 501 files `reader_limit`.
- `neurodeskorg/webapps`: full, 7,800 rows; 34 files `reader_limit`.

**Fetch routes:**
- Over all 497 done rows, the git pack served 179,037 files for 27 datasets, and 154,030 files came over HTTP.
- `nvidia/PhysicalAI-WorldModel-Synthetic-Autonomous-Driving-Scenarios` took 4.2 h in the first scan from a cut-off list. With the full list it read 121,076 files from one git pack in 34 minutes.
- Repos of many tiny files that are not plain git blobs still take hours: `lyzenghq/banned-historical-archives` 3.9 h, `TGMR/one_pass_ingestion` 2.3 h. These are rescan times; three other rescan processes shared the anonymous API allowance with them.

### What the first scan got wrong

The rescan (107 rows) replaced the first scan's results for these. First scan → now:

| | first scan | after the fixes |
|---|---|---|
| Tier B failed | 6 (3 datasetvet bugs: nanosecond timestamps, `ArrowIndexError` ×2) | 3 (all no longer on the Hub) |
| Tier B original-file scans from a file list cut at 100,000 entries | 64 (18 labelled "Full scan") | 0. The Hub's tree API is paged when `siblings` has 100,000 entries; a list that still cannot be read whole gives "Partial scan" (none in this run) |
| Full scans / samples / `not checked` | 195 / 197 / 102 | 190 / 204 / 103. With the whole file list, 6 "full" became samples and 1 sample became full; `gradio/frontend` has no data files |
| "corrupt" found | 47; 38 were tokenizer or config `.json` files read as data | "could not be read as rows": 40, each file with its kind, non-data files skipped. 11 of the 47 now find none |
| Tier A false "missing file" results | 157 in 8 repos (the paths existed beyond the cut-off) | 0 |
| Datasets with a dead link | 23 of 168 (13.7%) | 16 of 166 (9.6%) |
| Duplicates / leakage, over datasets with a row read | 74 of 353 (21.0%) / 24 of 353 (6.8%) | 73 of 356 (20.5%) / 24 of 356 (6.7%) |

Among the 99 rescanned Tier B datasets, the duplicates result changed for 11 (4 from `found` to `none found`, 3 the other way, 4 that had failed or now have no data files), and leakage for 6.

**Not rescanned.** Another 128 Tier A datasets had a cut-off file list but no missing-file result (`tier_A_cut_off_not_rescanned` in `rescan-set.json`). Only a licence file beyond the first 100,000 entries could change their results. The owner kept the rescan to the 8 with false results, so for these 128 a licence file past the cut-off would have been missed.

### Time for a very large repo (measured 2026-11-22)

The rescan ran four processes at once, so its per-repo times (20 to 50 minutes for a 100,000+ file repo) say little about one user. This is one repo, run alone: `PGCodeLLM/radin-cyber-backups` at `bc10089`, **389,052 files** (146,744 of them data files: `default/test` 6,307, `default/train` 136,099 and `default/validation` 4,338 files, plus the files not read as data). It is larger than 100,000 files, so the figures below are also given per file and per page for scaling. Each step ran in its own process with its own cache (`launch/time_large.py`; raw numbers in `launch/results/timing-PGCodeLLM__radin-cyber-backups.json`).

**This was the only measurement made logged in** (the owner allowed it for this one run; the token raises the API allowance). Everything else in this file was anonymous. Anonymous listing was not timed alone: the limit is 500 calls per 5 minutes, which covers the 100 pages of a 100,000 file repo, but a 389,052 file repo (616 calls) would make an anonymous run wait for the window.

| Step | Measured | Per unit | At 100,000 files |
|---|---|---|---|
| Listing, paged tree API, cold cache | **223.8 s** (615 pages of 1,000 files, 616 calls) | 0.36 s a page | about 36 s |
| Launch-style sample read (100 MB download cap, 10,000 rows), listing already cached | **321 s**: 9,999 rows, 75.9 MB read, 1,059 calls (527 files over HTTP; the one-fetch git route was not used because it would have been 33.7 GB) | | the sample stops at its row quota, so it does not grow with the file count; about 5 minutes |
| Default read (no download cap, 1,000,000-row sample quota), listing already cached | **stopped at the 20-minute cap** without finishing. `default/test` (6,307 files) took 218.6 s; `default/train` (136,099 files) had been running for 963 s when stopped | 34.7 ms a file (28.9 files a second) on `default/test` | about 58 minutes, extrapolated |

**Projected total for the default read of this repo: about 85 minutes** (146,744 files at 34.7 ms), plus the 4 minutes to list it. How far `default/train` had got when it was stopped is not known: the reader prints one line per split, not per file. The projection comes from one split's rate, and a split with bigger files would be slower, so it is an estimate, not a measurement. For a repo with 100,000 data files the same rate gives about **1 hour**.

What this means for users: for a repo of this size the listing is about a minute, a sampled read is about 5 minutes, and a full read is about an hour or more. The owner's decision (Phase 4.5): the README says so, and Phase 5 task 5.9 adds a warning before scanning a repo with 100,000 or more files (file count, estimated time, a sampled scan as the suggestion).

---

## 3. Limits

- **Anonymous runs.** No HF token was visible to `huggingface_hub` (no `HF_TOKEN`, nothing at `C:\Users\melsa\.cache\huggingface\token`), so gated cards and gated data are not readable. 8 eval rows were excluded for that reason. With a token, the HF API allowance doubles.
- **GitHub, anonymous.** Only the 9 standard licence file names are tried at HEAD. A repo without one is `unknown`, not `missing`.
- **Answer-key drift.** The key is a 2024 snapshot. Q1/Q3 use audit-time card revisions, but GitHub sources are read today.
- **Scanner coverage.** The built-in matcher knows only SPDX-listed licences and exact names. Non-SPDX terms and paraphrases ("research use only") give `unknown`.
- **Disagreement audit not done.** The 30-row samples await the owner's labels.

- **Launch scan, anonymous.** The README text of 31 gated datasets and the data of 30 were not read; with a token and accepted terms they could be.
- **Launch limits, not defaults.** Tier B's 100 MB / 10,000 rows / 100 MB cap were chosen to fit one laptop in about a day. A default `datasetvet check` scans up to 5 GB in full. Its counts would be higher for the 204 sampled datasets, and the 37 samples that stopped at the cap before reading a row would be read.
- **128 Tier A datasets not rescanned** after the listing fix (section 2): a licence file beyond their first 100,000 files would have been missed.
- **"Could not be read as rows" is about datasetvet's reader** as much as the data: 24 datasets have files with mixed types per column, which a valid file can have.
- **Snapshot.** Each result is for the frozen sha. The Hub changes daily: 3 of the 500 were gone within two days, and one repo's storage no longer serves 59,957 of its listed files.
- **Two code versions.** Rows not rescanned were made by the first scan's code (Tier A `1d8f4e4`, with the earlier config-hash method; Tier B `cdb210e`); rescanned rows by `4085159`. Each row's config hash is in the state and in `summary.json`.
