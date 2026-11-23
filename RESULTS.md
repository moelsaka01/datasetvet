# datasetvet: results (v2 licence rules, Phase 5.5)

All numbers here come from the **v2** licence rules (frozen as `eval-config-v2`) unless a section says otherwise. The v1 results from Phases 4 and 5 are in section 5, kept as the record and marked as superseded.

Facts only, not legal advice. Every Hugging Face call was **anonymous**: no token was visible to `huggingface_hub`, and where a token existed on the laptop it was hidden on purpose (`HF_TOKEN_PATH` set to a file that does not exist). The one exception is the timing of a very large repo (section 3, last part). No `GITHUB_TOKEN` was set. Measured 2026-11-19 to 2026-11-23 on the owner's Windows 11 laptop (Python 3.12.10), SPDX licence list 3.29.0, ScanCode toolkit 32.5.0.

## Headline

### What the scan found that the HF licence tag can't tell you

The 500 most-downloaded Hugging Face datasets by 30-day downloads (list frozen 2026-11-19; each read at its pinned commit; built-in matcher). Ranges are 95% Wilson intervals. Section 3 has the method.

| | result |
|---|---|
| Card states **no licence** | **36.6%** (182 of 497; 32.5–40.9%) |
| Card licence confirmed by another place (README text, a repo licence file or a stated source), nothing differing | 41.9% (132 of the 315 cards with a licence; 36.6–47.4%) |
| A README, repo licence file or stated source names a **different** licence | 6.3% (20 of 315; 4.1–9.6%) |
| Datasets with a **dead link**, of those with links checked | 10.5% (18 of 172; 6.7–15.9%) |
| **Exact duplicate rows** within a split, of 356 datasets with rows read | 20.5% (73; 16.6–25.0%); a lower bound for samples |
| The same input in two splits (**train/test leakage**) | 6.7% (24 of 356; 4.6–9.8%) |

Each dataset gets facts, not a grade. Apart from "states no licence", none of these can be seen from the `license:` tag. The tag only says what the card claims.

### How accurate the licence status is

The licence status was measured in two ways, reported side by side:

| | held-out set (64 rows scored) | DPI key, old test split (245 rows; **no longer blind**) |
|---|---|---|
| Who labelled it | **AI-assisted labels, every row reviewed and corrected by the author against the pinned cards** | the Data Provenance Initiative's hand audit (2024), the independent human key |
| datasetvet v2: rows agreeing (abstaining = miss) | 52 (81.2%; 70.0–88.9%) | 177 (72.2%; 66.3–77.5%) |
| HF `license:` tag alone: rows agreeing | **58** (90.6%; 81.0–95.6%) | **179** (73.1%) |
| ScanCode alone: rows agreeing | 23 (35.9%) | not run on this split for v2 |
| datasetvet v2: abstention (`unknown`) | 9.4% (4.4–19.0%) | 6.5% |
| datasetvet v2: Cohen's kappa, decided rows | 0.63 (bootstrap 0.28–0.87) | 0.46 (0.34–0.58) |
| HF tag alone: kappa | 0.54 (0.17–0.83) | 0.34 (0.23–0.45) |
| datasetvet v2: `inconsistent` found (recall) | 2 of 6 | 9 of 57 |

**The pre-registered goal was missed.** Of its four parts, v2 meets three: kappa ≥ 0.61, abstention < 15%, and beating ScanCode (p = 2e-6). It does not beat the HF tag alone. On both sets **the tag alone agrees with the labels on more rows than datasetvet**: on the held-out set datasetvet is right on 2 rows the tag gets wrong, and the tag on 8 that datasetvet gets wrong (exact McNemar p = 0.11, so not a significant difference either way). The tag can never say `inconsistent`. It does well on agreement because most cards are consistent with their labels. datasetvet's kappa is higher because it finds some of the contradictions, but it finds few of them (low recall) and flags some consistent cards as `inconsistent`. Section 1 has the details.

"Agreement" is agreement with a set of labels, not accuracy against a ground truth. The DPI calls its own labels self-reported and best-effort; the held-out labels were made by the author of the tool (section 1, "Labels").

---

## 1. Licence status: held-out evaluation (pre-registered)

### The goal, registered before any rule work

PLAN.md §8.1, commit `ed0ad4d`. On a fresh held-out set, v2 (built-in matcher) must reach:
- Cohen's kappa ≥ 0.61 on decided rows;
- abstention < 15%;
- more agreeing rows than baseline A (the HF `license:` tag alone) and baseline B (ScanCode alone), each with an exact McNemar p < 0.05.

The old test split was retired from tuning at the same time.

| part of the goal | result | met |
|---|---|---|
| kappa ≥ 0.61, decided rows | **0.626** (58 rows; bootstrap 95% CI 0.28–0.87) | yes; the interval is wide |
| abstention < 15% | **9.4%** (6 of 64; 4.4–19.0%) | yes; the upper bound is above 15% |
| beats B (ScanCode alone) | 34 rows right only with datasetvet, 5 only with B; p = 2.4e-6 | yes |
| beats A (HF tag alone) | 2 rows right only with datasetvet, **8 only with A**; p = 0.11 | **no** |
| **goal** | | **missed** |

### Held-out set

- **Draw:** 120 datasets from `random.Random(20261122).sample()` over the 492 launch-list datasets that are not in the DPI collection (7 were) and still exist (1 did not: `KakologArchives/KakologArchives`).
- **Labelling sheet** (`eval/holdout/sheet.csv`): card fields copied verbatim at the pinned sha, pinned links, the URLs found in the card, and the gated flag. It holds no datasetvet output.
- **Freeze order:** the sheet was committed and tagged `holdout-v1` (`eb8bfad`) before any label existed. The rules, the runners, both baselines and the scorer were then frozen as `eval-config-v2` (`45122c5`). `predict.py` refuses to run off the tag, on an incomplete sheet, or when a column other than the four label columns has changed since `holdout-v1`.
- **Label rules:** the DPI definitions, in `eval/holdout/LABELLING.md`.
- **Rows scored:** 64 of the 120: 54 `consistent`, 6 `inconsistent`, 4 `missing`. Excluded: 25 `card unreadable` (24 repos with no README at the frozen sha, and `defeatbeta/yahoo-finance-data`, deleted since), 17 where an expert licence is not on the SPDX list, and 14 where the labeller found no licence stated anywhere. 64 is at least 60, so the second batch the pre-registration allowed for was not drawn.

### Labels

**AI-assisted labels, every row reviewed and corrected by the author against the pinned cards.** ChatGPT made a first pass over all 120 rows. In many rows that pass read the current cards, not the pinned ones: 108 of its notes mention a current or latest card. The author then checked every row against the frozen card copies (`eval/holdout/cards/`, not in the repository; their SHA-256 hashes are in the sheet) and corrected it.

| compared with the AI first pass | rows changed, of 120 |
|---|---|
| `expected_status` | **12** |
| `expert_licences` | **12** (the same 12 rows) |
| `confidence` | 33 |

Of the 64 scored rows, 60 have the same status and licences as the first pass and 4 were changed by the author. These labels are **not an independent human audit**: the author built the tool, and the labels started from an AI draft. The DPI comparison (section 2) is the independent human key.

**Deviations from the pre-registration** (stated here, not corrected after the fact):
1. **AI in the label step.** The pre-registration says "no AI in any rule, baseline or label step" and that the owner applies the labels. The labels started from an AI first pass (above).
2. **24 repos with no README.** `LABELLING.md` keeps `excluded: card unreadable` for a card that cannot be fetched at all. These 24 have no README at the frozen sha (HTTP 404), so its rules would label them `missing` or `excluded: expert none`. They were labelled `card unreadable`. A, B and C all say `missing` on all 24, so the choice removes the same easy agreements from all three. **Sensitivity check (not pre-registered):** with the 24 counted as `missing`, A agrees on 82 of 88 rows, C on 76 and B on 47. The paired results are unchanged (C vs A: 2 against 8), and so is the outcome: goal missed, not beating A.
3. **Subsets.** The `confidence = sure` subset and the split by changed labels were asked for after labelling. They are exploratory.

### Results

Predictions: `eval/results/holdout/predictions.jsonl` (`predict.py` in the ScanCode venv). Metrics: `eval/results/holdout/metrics.json` (`score.py`).

| | A: tag alone | B: ScanCode alone | **C: datasetvet v2** |
|---|---|---|---|
| rows agreeing, abstaining = miss | **58 of 64** (90.6%; 81.0–95.6%) | 23 (35.9%; 25.3–48.2%) | 52 (81.2%; 70.0–88.9%) |
| abstention | 0% | 45.3% (29; 33.7–57.4%) | 9.4% (6; 4.4–19.0%) |
| agreement, decided rows | 90.6% (58/64) | 65.7% (23/35; 49.2–79.2%) | 89.7% (52/58; 79.2–95.2%) |
| kappa, decided rows (bootstrap 95%) | 0.54 (0.17–0.83) | 0.42 (0.15–0.66) | **0.63** (0.28–0.87) |
| `inconsistent`: precision / recall | never says it / 0 of 6 | 4 of 15 / 4 of 6 | 2 of 7 / 2 of 6 |
| exact McNemar vs C | C only 2, A only 8; p = 0.11 | C only 34, B only 5; p = 2.4e-6 | |

Confusion matrices (rows: expected; columns: the configuration's status):

| A: tag alone | consistent | inconsistent | missing | unknown |
|---|---|---|---|---|
| consistent | **54** | 0 | 0 | 0 |
| inconsistent | 6 | **0** | 0 | 0 |
| missing | 0 | 0 | **4** | 0 |

| B: ScanCode alone | consistent | inconsistent | missing | unknown |
|---|---|---|---|---|
| consistent | **15** | 11 | 0 | 28 |
| inconsistent | 1 | **4** | 0 | 1 |
| missing | 0 | 0 | **4** | 0 |

| C: datasetvet v2 | consistent | inconsistent | missing | unknown |
|---|---|---|---|---|
| consistent | **46** | 5 | 0 | 3 |
| inconsistent | 1 | **2** | 0 | 3 |
| missing | 0 | 0 | **4** | 0 |

- **Where C loses to the tag (8 rows, all labelled `consistent`).** What made C's status, from `C_comparisons` in the predictions:
  - `inconsistent` from **licence files of vendored Python packages** in the repo (a committed `.venv` or `site-packages`, e.g. numpy's bundled licences): `jamie33/July`, `camel-ai/SETA-Env`.
  - `inconsistent` from a GitHub source repo's `LICENSE` naming a different licence, where the code-licence rule does not apply (both licences are software licences, or the card's is): `aisa-group/PostTrainBench-Trajectories`, `TIGER-Lab/MMLU-Pro`.
  - `inconsistent` from a `LICENSE` inside an asset folder (`assets/robots/gripper_2f_85/`): `HRDexDB/HRDexDB`.
  - `unknown` from two **`.py` files whose names contain "license"**, read as licence files and not identified: `XiaomiMiMo/MiMo-V2.6-RL-oss`.
  - `unknown` from README text the matcher could not identify (`espnet/yodas`) or that names a licence without a version (`google/fleurs`).
  - The first and fourth are reading errors, not judgements; they are on the v0.2 list (PLAN.md §11).
- **Where C beats the tag (2 rows):** `espnet/yodas3.1` and `yifengzhu-hf/LIBERO-datasets`, two real contradictions that the tag cannot show.
- **C's `consistent`:** 25 "confirmed" (another place states the same licence) and 22 "uncontradicted" (only the card states one).
- **Few contradictions.** With 6 `inconsistent` rows, recall and precision on that status are very uncertain (2 of 6 is 33%, 95% CI 10–70%).

### Subsets (exploratory, not pre-registered)

`eval/holdout_subsets.py` writes `eval/results/holdout/metrics-subsets.json`, using the frozen scorer's code.

| subset | rows scored | A agree | B agree | C agree | C abstention | C kappa | A kappa | C vs A |
|---|---|---|---|---|---|---|---|---|
| `confidence = sure` | 26 | 24 | 18 | 23 | 7.7% | 0.84 | 0.64 | C only 1, A only 2; p = 1.0 |
| `confidence = unsure` | 38 | 34 | 5 | 29 | 10.5% | 0.49 | 0.47 | C only 1, A only 6; p = 0.13 |
| label unchanged from the AI first pass | 60 | 55 | 22 | 48 | 10.0% | 0.58 | 0.59 | C only 1, A only 8; p = 0.04 |
| label changed by the author | 4 | 3 | 1 | 4 | 0% | 1.0 | 0.0 | C only 1; p = 1.0 |

On the rows the author was sure of (22 `consistent`, 2 `inconsistent`, 2 `missing`), datasetvet's kappa is higher. That subset is too small to separate it from the tag.

---

## 2. Licence status against the DPI key (independent human key)

### Method

- **Answer key** (`eval/build_key.py`, `eval/key/`): the DPI's `data_summaries/*.json` at commit `ce6662d` of `Data-Provenance-Initiative/Data-Provenance-Collection` (Apache-2.0). 109 files and 3,718 entries; 3,492 of them link to 792 unique HF repos.
  - 81 repos were dropped because their DPI entries disagree on the expert licence set, and 3 because they have no recorded card licence. That leaves 708 key rows.
  - DPI licence names were mapped to SPDX by hand (`eval/dpi_licence_map.csv`, 52 names).
- **Expected status:** the card's licence as the DPI recorded it at audit time (`HF Yaml License`), compared with the expert licence set.
  - `missing` if the card stated none; `consistent` if the two are equivalent SPDX expressions; `inconsistent` otherwise.
  - Excluded: 212 rows whose expert set is "none stated", and 125 whose expert licence is not on the SPDX list.
  - That leaves **371 rows: 239 consistent, 80 inconsistent, 52 missing.**
- **Card text as it was at audit time** (`eval/revisions.py`): for each repo, the latest commit on `main` at or before the last change to its DPI summary file (May–October 2024). datasetvet checks `hf:<id>@<that sha>`. GitHub sources are read at today's HEAD; they cannot be pinned to the audit date.
- **Split:** by hash of the repo id, 30% dev (118 rows) and 70% test (253 rows). 8 test rows are excluded because the repo's history is no longer readable anonymously, so 245 are scored.
- **Status per dataset (v2):** the `licence.summary` ("Licence, overall") result.

### v2 on the old test split (no longer blind)

**Not blind.** These 245 rows were scored in Phase 4, looked at again in Phase 5, and 48 of their datasets were used in the v2 rule work. Inputs: the same rows and the same audit-time card revisions as in Phase 4, run with the frozen v2 code (`eval/results/runs/test-v2.jsonl`, `eval/results/metrics-test-v2.json`). Baseline A here is the card's YAML licence at the audit revision (no licence → `missing`, any licence → `consistent`); it was not pre-registered for this split.

| | **v2** | A: tag alone |
|---|---|---|
| rows agreeing, abstaining = miss | 177 of 245 (72.2%; 66.3–77.5%) | **179** of 245 (73.1%) |
| abstention (`unknown`) | 6.5% | 0% |
| agreement, decided rows | 77.3% (71.4–82.2%) | 73.1% |
| kappa, decided rows (bootstrap 95%) | **0.46** (0.34–0.58) | 0.34 (0.23–0.45) |
| `inconsistent` precision / recall | 9 of 17 / **9 of 57** | never says it / 0 of 57 |

Confusion matrix, v2 (rows: expected; columns: v2):

| expected \ v2 | consistent | inconsistent | missing | unknown |
|---|---|---|---|---|
| consistent | **144** | 8 | 7 | 3 |
| inconsistent | 37 | **9** | 0 | 11 |
| missing | 0 | 0 | **24** | 2 |

- **v2 vs the tag alone:** 9 rows right only with v2, 11 only with A (p = 0.82): a tie on agreement, as on the held-out set. v2 has the higher kappa because A can never say `inconsistent`.
- **Where v2 is wrong.** 37 rows the key calls `inconsistent` get `consistent` from v2. 23 of them are "uncontradicted": nothing in the card's repo or its readable sources names another licence, and the DPI expert found one elsewhere (a paper, a homepage, upstream data). Rules that read only the card, the repo and GitHub cannot see that.
- **v2's `consistent`:** 181 rows; 128 "confirmed", 53 "uncontradicted" (30 of those match the key).
- **The 197 rows not used in rule work:** v2 agrees on 151; abstention 4.6%; kappa 0.55.
- **How it compares with v1:** v1 agreed on 139 of these 245 rows (45 right only with v2, 7 only with v1; exact McNemar p ≈ 7e-8) and abstained on 25.3%. Its kappa was higher (0.53), because v2's "uncontradicted" rule decides rows that v1 left `unknown`, some of them wrongly. Section 5 has the v1 tables.

### What changed in v2 (rules only, no AI)

These were tuned only on the dev split (118 rows) and the 48 datasets of the two Phase 4 disagreement samples, using the DPI key's labels (those samples have no owner labels). PLAN.md §5.2 "Phase 5.5" has the details.

1. **"The source code licence differs."** A stated source repo's licence file naming only OSI-approved licences, against a card naming a data licence (not OSI-approved), gives `unknown` with that fact, not `inconsistent`. Example: alpaca's card says CC-BY-NC-4.0, `github.com/tatsu-lab/stanford_alpaca` has an Apache-2.0 `LICENSE` and a CC-BY-NC-4.0 `DATA_LICENSE`.
2. **Software licences set aside in one text.** "Code MIT, data CC-BY-4.0" in a README is `consistent` with a CC-BY-4.0 card.
3. **One status per dataset** (`licence.summary`, "Licence, overall"). If the card states a licence and nothing read either confirms or contradicts it, the status is `consistent`, with the sub-fact **"uncontradicted, not confirmed"**.

The OSI-approved flag of the SPDX licence list is now the one licence property that decides something (rules 1 and 2).

**Rule-work rows (tuned on; not an accuracy claim).** 164 scored rows (116 dev, 48 from the disagreement samples, where v1 by construction scores badly). Rows agreeing with the key, abstaining counted as a miss (`eval/results/metrics-rulework-v2.json`):

| rules | agree | abstention | kappa, decided rows |
|---|---|---|---|
| before v2 | 84 of 164 | 29.3% | 0.50 |
| + uncontradicted | 109 | 7.3% | 0.42 |
| + code licence (data-licence card) | 92 | 31.7% | 0.62 |
| + code licence (any card) | 91 | 31.7% | 0.60 |
| all three, data-licence card (**frozen**) | **119** | **7.3%** | **0.50** |
| all three, any card | 118 | 7.3% | 0.48 |
| all but the set-aside rule | 117 | 8.5% | 0.50 |

Each rule passes the pre-stated test: it raises the number of agreeing rows. Kappa does not improve.

---

## 3. Launch scan: top 500 Hugging Face datasets

**Code.**
- **Tier A** (card, licence, provenance, links): all 500 rescanned with the v2 code at `2a63683`, config hash `14b429ea97a2357a`. Run 2026-11-22 18:26 to 23:43 (+04:00), 3 processes (`--shard I/3`), 48,898 s of checking, 25,493 requests, anonymous.
- **Tier B** (data health): first scan on `cdb210e` (config hash `2472d09329f26eb6`), with 99 rows rescanned on `4085159` (`fe7d94fb698d5f41`) after the Phase 4.5 fixes. The v2 licence rules do not affect data health, so Tier B was not re-run.
- **What the config hash covers.** It includes the git tree ids of `src/`, `launch/run.py`, `launch/state.py` and `pyproject.toml`. `launch/run.py` refuses to run with uncommitted changes there, so every finished row names the committed code that made it.
- Every request obeys the Hub's `RateLimit` headers and waits out 429s.

### Method

- **List** (`launch/freeze_list.py`, `launch/lists/top500-2026-11-19.json`): the 500 most-downloaded datasets by the Hub's 30-day count on 2026-11-19 at 21:11 (+04:00), each pinned to its commit sha. Sizes came from the Dataset Viewer `/size` for 251 of them (291 TB of Parquet together).
- **Every check reads `hf:<id>@<frozen sha>`**, anonymously, through one rate-limited HTTP client per process.
- **Tier A** (all 500): card fields, licence consistency (built-in matcher), provenance to depth 2, links. No data is downloaded. A file list cut at 100,000 entries is paged through the tree API, so every file is seen.
- **Tier B** (all 500): data health only, with launch limits chosen from the measured budget, not the tool's defaults: a full scan when a dataset's data is ≤ 100 MB; otherwise a seeded sample of 10,000 rows (seed 0) in small chunks across each file read, with at most 100 MB downloaded.
- **First Tier B scan:** 2026-11-20 14:34 to 2026-11-21 06:35 (+04:00), 3 parallel processes in 3 rounds, 75,801 s of checking, 602,535 requests, no 429. **Tier B rescan** (2026-11-21): 99 datasets chosen by `launch/rescan_set.py` (`launch/results/rescan-set.json`), 81,537 s, 317,975 requests.
- **State** (`launch/state.sqlite`, not in the repository): one row per dataset and tier, holding the report, the config hash and the time. `launch/summarize.py` writes `launch/results/datasets.csv` (one row per dataset, facts only) and `launch/results/summary.json` (the config hashes behind each tier's rows). The first scan's table and summary are kept in `launch/results/first-scan/`.

### Tier A: cards, licences, provenance, links

| | count |
|---|---|
| Checked | 497 of 500. Three are gone: `KakologArchives/KakologArchives` (frozen sha returns HTTP 404), `defeatbeta/yahoo-finance-data` and `HubLabs/HubEgo-100K` (deleted or made private after the list was frozen) |
| Gated | 30. The card metadata from the API and the links are checked; the README text and the files are not readable anonymously |
| Card licence `present` | 315 (63.4%; 59.1–67.5%) |
| Card licence `missing` | **182 (36.6%; 32.5–40.9%)** |

**Licence, overall** (one status per dataset, for the 315 cards with a licence):

| overall status | datasets | share (95% CI) |
|---|---|---|
| `consistent`, confirmed (another place states the same licence, none differs) | 132 | 41.9% (36.6–47.4%) |
| `consistent`, uncontradicted (only the card states one) | 82 | 26.0% (21.5–31.1%) |
| `inconsistent` (a README text, licence file or source names a different licence) | 20 | 6.3% (4.1–9.6%) |
| `unknown`, card unclear (the card's licence is not one SPDX licence: `other`, a family id, a non-SPDX id) | 64 | 20.3% (16.2–25.1%) |
| `unknown`, unresolved (a comparison could not be made) | 17 | 5.4% (3.4–8.5%) |

All comparisons together: 225 `consistent`, 53 `inconsistent`, 301 `missing`, 290 `unknown`. Section 1 applies: on the held-out set, datasetvet's `inconsistent` was right for 2 of 7 datasets and found 2 of 6 contradictions. An `inconsistent` here is a difference to look at, not a finding.

**Provenance:** 11 datasets declare parents (`source_datasets`), giving 14 comparisons: 2 `inconsistent`, 4 `missing`, 8 `unknown`.
- `EleutherAI/lambada_openai`: card MIT, parent `cimec/lambada` CC-BY-4.0.
- `jat-project/jat-dataset`: card Apache-2.0, parent `oscar-corpus/oscar` CC0-1.0.

**Links:** 1,008 checked in 172 datasets: 413 `ok`, 575 `dead`, 10 `restricted`, 7 `unreachable`, 3 `unknown`.
- 564 of the 575 `dead` are card `configs[].data_files` paths that match no file in the repo ("missing file"). 550 of them are in `HuggingFaceFW/fineweb-2`: its card declares a test split for 550 languages that have only a train file (checked: `data/abi_Latn/` holds only `train/000_00000.parquet`).
  - The others: `applied-ai-018/pretraining_v1-omega` (5), `lmms-lab/LLaVA-Video-178K` (4), `3dcodeverse/3dcodeverse-2m` (2), `McGill-NLP/WebLINX-full` (1, checked against the tree API), `zdbfv/M3_VOS` (1) and `HenryYHW/ADAS-TO` (1).
  - The last three repos are new in this run: their cards were not read in the first scan (below). Their paths were not checked by hand.
- 11 are dead URLs in 11 datasets.
- Datasets with at least one dead link: **18 of 172 (10.5%; 6.7–15.9%)**.

### Tier B: data health

| | datasets |
|---|---|
| Data health run | 394: 190 full scans, 204 samples (135 samples stopped at the 100 MB download cap) |
| At least one row read | **356** (189 full, 167 samples). The other 38: 37 samples that stopped at the 100 MB download cap before reading a row, and 1 full scan (`stair-lab/nonmyopia_results`) whose 7,527 files could not be read as rows |
| Read from | 232 HF's Parquet conversion, 162 the original files |
| `not checked` | 103: 58 no Parquet conversion and no Parquet/CSV/JSON Lines files; 30 gated; 14 Dataset Viewer turned off by the owner and no `configs` in the card; 1 (`gradio/frontend`) whose only JSON files are front-end and package files |
| Failed | 3, the datasets no longer on the Hub |
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
- **Files that could not be read as rows** (`health.unreadable`). Files that are not data (tokenizer and config JSON, package metadata, dependency folders) are skipped. Each file gets a kind:
  - `reader_limit` (24 datasets): valid files with more than one type in a column;
  - `invalid` (19): the content does not parse as its file type;
  - `empty` (12): no rows;
  - `download` (1): `lyzenghq/banned-historical-archives`, where 59,957 listed files return HTTP 404 from the Hub's storage.
  - None of these means the data is damaged; the report says so for each file.
- **Fetch routes:** over all 497 done rows, the git pack served 179,037 files for 27 datasets, and 154,030 came over HTTP. Repos of many tiny files that are not plain git blobs still take hours (`lyzenghq/banned-historical-archives` 3.9 h).

### What earlier scans got wrong

| | earlier scan | now |
|---|---|---|
| **Card licence `missing`** | 200 of 499 (40.1%) in the first Tier A scan | **182 of 497 (36.6%)**. In 18 repos whose file list was cut at 100,000 entries, the first scan did not find `README.md` and reported "no card". All 18 were among the 128 cut-off repos not rescanned in Phase 4.5; the v2 run reads every one, and each states a licence. Found by comparing the v1 and v2 tables before launch |
| Tier B failed | 6 (3 datasetvet bugs) | 3 (all no longer on the Hub) |
| Tier B original-file scans from a file list cut at 100,000 entries | 64 (18 labelled "Full scan") | 0 |
| "corrupt" found | 47; 38 were tokenizer or config `.json` files read as data | "could not be read as rows": 40, each file with its kind |
| Tier A false "missing file" results | 157 in 8 repos (the paths existed beyond the cut-off) | 0 |
| Datasets with a dead link | 23 of 168 (13.7%) in the first scan | 18 of 172 (10.5%) |
| Duplicates / leakage, over datasets with a row read | 74 of 353 / 24 of 353 | 73 of 356 / 24 of 356 |

### Time for a very large repo (measured 2026-11-22)

One repo, run alone: `PGCodeLLM/radin-cyber-backups` at `bc10089`, **389,052 files** (146,744 of them data files). Each step ran in its own process with its own cache (`launch/time_large.py`; raw numbers in `launch/results/timing-PGCodeLLM__radin-cyber-backups.json`). **This was the only measurement made logged in** (the owner allowed it for this one run; the token raises the API allowance). Anonymous listing was not timed alone: the limit is 500 calls per 5 minutes, which covers the 100 pages of a 100,000-file repo but not the 616 calls of this one.

| Step | Measured | Per unit | At 100,000 files |
|---|---|---|---|
| Listing, paged tree API, cold cache | **223.8 s** (615 pages of 1,000 files, 616 calls) | 0.36 s a page | about 36 s |
| Launch-style sample read (100 MB download cap, 10,000 rows), listing cached | **321 s**: 9,999 rows, 75.9 MB read, 1,059 calls | | the sample stops at its row quota; about 5 minutes |
| Default read (no download cap, 1,000,000-row sample quota), listing cached | **stopped at the 20-minute cap**. `default/test` (6,307 files) took 218.6 s | 34.7 ms a file on `default/test` | about 58 minutes, extrapolated |

Projected total for the default read of this repo: about 85 minutes (146,744 files at 34.7 ms), plus the 4 minutes to list it. This is an estimate from one split's rate, not a measurement. For a repo with 100,000 data files the same rate gives about 1 hour. datasetvet warns before scanning a repo with 100,000 or more files.

---

## 4. Limits

- **The author labelled the held-out set, starting from AI drafts.** The author changed `expected_status` in 12 of the 120 rows and `expert_licences` in the same 12; 4 of the 64 scored rows were changed. These are not independent labels. The DPI comparison (section 2) is the independent human key, but it is no longer blind for v2.
- **Contradiction recall is low.** datasetvet found 2 of the 6 contradictions in the held-out set and 9 of the 57 in the DPI key's old test split. Most contradictions the labellers found are in places the rules do not read (papers, homepages, upstream data), or come from a judgement about which licence covers the data. A card with no contradiction found is not shown to have none. On the v0.2 list (PLAN.md §11).
- **The HF tag alone agrees as often or more.** On both evaluations the tag alone agrees with the labels on as many rows as datasetvet, or more. datasetvet's value is in what the tag can't show: confirmed and contradicting sources, dead links, duplicates and leakage. For a single consistent/not label, it is not better than reading the tag.
- **Small held-out set.** 64 scored rows, 6 of them `inconsistent`. Every interval above is wide.
- **Anonymous runs.** Gated cards and gated data are not readable: the README text of 30 gated launch datasets and their data were not read, and 8 DPI rows were excluded.
- **GitHub, anonymous.** Only the 9 standard licence file names are tried at HEAD. A repo without one is `unknown`, not `missing`. GitHub sources are read today, not at the audit date.
- **Scanner coverage.** The built-in matcher knows only SPDX-listed licences and exact names. Non-SPDX terms and paraphrases ("research use only") give `unknown`.
- **Disagreement audit not done.** The two Phase 4 samples of 30 disagreements each (section 5) still await the owner's labels.
- **Launch limits, not defaults.** Tier B's 100 MB / 10,000 rows / 100 MB cap were chosen to fit one laptop in about a day. A default `datasetvet check` scans up to 5 GB in full; its counts would be higher for the 204 sampled datasets.
- **"Could not be read as rows" is about datasetvet's reader** as much as the data: 24 datasets have files with mixed types per column, which a valid file can have.
- **Snapshot.** Each result is for the frozen sha. The Hub changes daily: 3 of the 500 were gone within three days.
- **Two code versions in the launch table.** Tier A rows are all from `2a63683`; Tier B rows from `cdb210e` or `4085159`. Each row's config hash is in `summary.json`.

---

## 5. History: v1 rules (Phases 4 and 5), superseded

These are the results of the **v1** licence rules, frozen as `eval-config-v1` (`1d8f4e4`). They are kept as the record. The current rules are v2 (sections 1 and 2).

### DPI test split, v1 (blind when it was run)

Only each scanner's thresholds were tuned, on dev only. Built-in: all 8 grid points gave the same 79 of 116 dev rows, so it stayed at 0.90 / 0.95. ScanCode: score ≥ 50 gave 76 (≥ 90 gave 66), so 50. Status per dataset: card states no licence → `missing`; else any comparison `inconsistent` → `inconsistent`; else any `consistent` → `consistent`; else `unknown`.

| | built-in matcher | ScanCode (score ≥ 50) |
|---|---|---|
| Agreement, decided rows | 76.0% (139 of 183; 69.3–81.6%) | 74.9% (131 of 175; 67.9–80.7%) |
| Abstention (`unknown`) | 25.3% (62 of 245) | 28.6% (70 of 245) |
| Agreement counting abstentions as misses | 56.7% (139 of 245; 50.5–62.8%) | 53.5% (131 of 245; 47.2–59.6%) |
| Cohen's kappa, decided rows | 0.53 | 0.52 |
| `inconsistent`: precision / recall | 16/43 / 16/57 | 15/44 / 15/57 |

**built-in matcher, v1** (rows: expected; columns: ours)

| expected \ ours | consistent | inconsistent | missing | unknown |
|---|---|---|---|---|
| consistent | **99** | 27 | 7 | 29 |
| inconsistent | 10 | **16** | 0 | 31 |
| missing | 0 | 0 | **24** | 2 |

**ScanCode, v1**

| expected \ ours | consistent | inconsistent | missing | unknown |
|---|---|---|---|---|
| consistent | **92** | 29 | 7 | 34 |
| inconsistent | 8 | **15** | 0 | 34 |
| missing | 0 | 0 | **24** | 2 |

Per-row data: `eval/results/runs/test.jsonl`; metrics: `eval/results/metrics-test.json`.

- **Card parsing at the audit-time revision.** Our card licence matched the DPI's recorded value in 225 of 245 rows (91.8%; 87.7–94.7%). The mismatches are mostly about how the value was recorded: one value kept from a multi-licence list, a specific licence recorded for an HF family id, and 7 cards with no `license` key at the chosen revision.
- **Source licences.** For the 45 test rows where we read a GitHub source and the DPI recorded a GitHub licence, our detection agreed in 45 of 45 (both scanners; 92.1–100%).
- **What drove v1's `inconsistent`:** 33 from a GitHub source's LICENSE, 14 from the README text. A source repo's LICENSE often covers its code, not the data. That finding led to v2's code-licence rule.

### ScanCode threshold, 50 against 90 (Phase 5, a second look at the test split)

| ScanCode threshold | rows agreeing, abstaining = miss | abstention | agreement, decided rows | kappa |
|---|---|---|---|---|
| ≥ 50 (default) | **131 of 245** | 28.6% | 74.9% | 0.52 |
| ≥ 90 | 110 of 245 | 39.2% | 73.8% | 0.51 |

22 rows agree only at 50 and 1 only at 90 (exact sign test, p ≈ 6e-6). The gain is from fewer abstentions, not a looser reading. `SCANCODE_MIN_SCORE` is 50.

### Human audit of v1's disagreements (not labelled)

`eval/results/disagreements-builtin.csv` and `disagreements-scancode.csv` hold 30 randomly chosen v1 disagreements each (seed 4), with a column for the owner's label (*ours wrong / key wrong / changed since audit / ambiguous*). They are still unlabelled; `python eval/audit.py` refuses while any row is empty. No breakdown is published and none is invented.
