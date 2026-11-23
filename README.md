# datasetvet

[![ci](https://github.com/moelsaka01/datasetvet/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/moelsaka01/datasetvet/actions/workflows/ci.yml?query=branch%3Amain)

**Before you train on it, check it.**

A free, local command-line tool that checks a Hugging Face dataset for what its `license:` tag can't tell you:
- whether the README text, the repo's licence files and the sources the card points to **agree with the card's licence**;
- whether the card states a licence at all;
- **dead links** and `data_files` paths that match no file;
- **exact duplicate rows** within a split, and the same input in two splits (**train/test leakage**);
- empty rows and PII-pattern matches.

It writes a report of **verifiable facts**, each with an evidence link pinned to a commit. It does not call a dataset good or bad, and **it is not legal advice**.

![A datasetvet run on tatsu-lab/alpaca](https://raw.githubusercontent.com/moelsaka01/datasetvet/main/docs/demo/demo.gif)

*A real run on `tatsu-lab/alpaca`, recorded in real time (about 12 seconds, uncached, on a laptop). Replay the recording with `asciinema play docs/demo/demo.cast`.*

## Quick start (30 seconds)

```powershell
pip install datasetvet
datasetvet check hf:stanfordnlp/imdb
```

Add `--json report.json` or `--md report.md` to keep the report. It uses free endpoints only. If you are logged in with `hf auth login` (or set `HF_TOKEN`), your token raises the Hub's rate limits; it is sent only to Hugging Face hosts and is never printed or stored.

## What a report looks like

An excerpt of a real report (`datasetvet check hf:tatsu-lab/alpaca`, 2026-11-23, trimmed):

```text
Licence consistency (overall consistent; comparisons: 2 consistent, 1 unknown)
  consistent   Licence, overall
               Card says cc-by-nc-4.0 (SPDX CC-BY-NC-4.0) (README.md@dce01c9, YAML line 2); confirmed by the
               README text and source github.com/tatsu-lab/stanford_alpaca DATA_LICENSE, and no comparison
               differs.
               Not counted as a contradiction (the source code licence differs): source
               github.com/tatsu-lab/stanford_alpaca LICENSE.
  consistent   Card vs README text
               ... README.md@dce01c9 (text below the YAML) says CC-BY-NC-4.0 (name, line 130); these are
               the same licence.
  unknown      Card vs source github.com/tatsu-lab/stanford_alpaca LICENSE
               ... github.com/tatsu-lab/stanford_alpaca LICENSE@761dc5b says Apache-2.0 (full text, score 98,
               lines 1-201); the source code licence differs: Apache-2.0 is an OSI-approved software licence
               of the repo github.com/tatsu-lab/stanford_alpaca, and its licence file does not say whether it
               covers the data.
  consistent   Card vs source github.com/tatsu-lab/stanford_alpaca DATA_LICENSE
               ... says CC-BY-NC-4.0 (full text, score 99, lines 1-407); these are the same licence.

Data health (Full scan)
  none found   Duplicate rows within a split
               default/train: no duplicate rows in 52,002 rows scanned.
  found        PII pattern matches
               default/train, column output: 36 values match the email pattern (e.g. j***@e***.com, ...)
               These are pattern matches, not a finding of personal data. Examples are masked.

Facts only, not legal advice. Licence statuses: consistent / inconsistent / missing / unknown.
No check here judges how this data can be used.
```

Every fact has an evidence link pinned to a commit. The source repo's `LICENSE` names a software licence (OSI-approved on the SPDX list) while the card names a data licence, so it is reported as "the source code licence differs", not as a contradiction; its `DATA_LICENSE` matches. The "overall" line gives one status per dataset. When only the card states a licence and nothing read agrees or differs, it says `consistent` with "uncontradicted, not confirmed".

## What it checks

- **Card:** licence field present and a valid id, required metadata, citation, stated source.
- **Licence consistency:** the card's licence compared with the README text, the repo's licence files, and the licence of each source the card points to. Four statuses only: *consistent*, *inconsistent*, *missing*, *unknown*.
- **Provenance:** the licences of declared parent datasets, side by side.
- **Links:** dead source URLs and `data_files` paths that match no file.
- **Data health:** exact duplicates within a split, leakage across splits, empty rows, files that could not be read as rows, label balance, PII-pattern matches. A full scan by default; large datasets are sampled, and the report always says which.

## What we found in the top 500

We ran it on the 500 most-downloaded Hugging Face datasets (list frozen 2026-11-19, each read at its pinned commit, built-in matcher, anonymous). Ranges are 95% Wilson intervals. Per-dataset facts are in [`launch/results/datasets.csv`](https://github.com/moelsaka01/datasetvet/blob/main/launch/results/datasets.csv); how it was done and what it does not show is in [RESULTS.md section 3](https://github.com/moelsaka01/datasetvet/blob/main/RESULTS.md#3-launch-scan-top-500-hugging-face-datasets).

| | result |
|---|---|
| Card states **no licence** | **36.6%** (182 of 497; 32.5–40.9%) |
| Card licence confirmed by another place (README text, a licence file or a stated source), none differing | 41.9% (132 of the 315 with a licence; 36.6–47.4%) |
| A README, licence file or stated source names a **different** licence | 6.3% (20 of 315; 4.1–9.6%) |
| Datasets with a **dead link**, of those with links checked | 10.5% (18 of 172; 6.7–15.9%) |
| **Exact duplicate rows** within a split, of 356 datasets with rows read | **20.5%** (73; 16.6–25.0%); a lower bound for samples |
| The same input in two splits (**train/test leakage**) | 6.7% (24 of 356; 4.6–9.8%) |
| PII-pattern matches (email, phone), of 258 with string columns | 25.6% (66; 20.6–31.2%) |

The data-health rows come from a launch scan with limits chosen for one laptop (full scan up to 100 MB, otherwise a 10,000-row sample), so they are lower bounds for the sampled datasets. 103 of the 500 could not be checked for data (no Parquet conversion, gated, or the Dataset Viewer turned off).

## How accurate is it?

**As a single consistent / not-consistent label, the licence status is no better than the HF `license:` tag alone.** We measured it in two ways, with a pre-registered goal:

| | held-out set, 64 rows | DPI key, 245 rows (**no longer blind**) |
|---|---|---|
| Labels | AI-assisted labels, every row reviewed and corrected by the author against the pinned cards | the Data Provenance Initiative's hand audit, the independent human key |
| datasetvet: rows agreeing | 52 (81.2%; 70.0–88.9%) | 177 (72.2%; 66.3–77.5%) |
| HF tag alone: rows agreeing | **58** (90.6%; 81.0–95.6%) | **179** (73.1%) |
| datasetvet answered `unknown` | 9.4% | 6.5% |
| Cohen's kappa, datasetvet / tag alone | 0.63 / 0.54 | 0.46 / 0.34 |
| Contradictions found by datasetvet (recall) | 2 of 6 | 9 of 57 |

- **The goal was missed.** datasetvet met the kappa (≥ 0.61) and abstention (< 15%) targets and beat ScanCode alone. It did not beat the tag alone: on the held-out set it was right on 2 rows the tag got wrong, and the tag on 8 that it got wrong (p = 0.11).
- **Why the tag ties or wins.** The tag can never say "inconsistent", and most cards are consistent with their labels. datasetvet finds some contradictions the tag cannot show, which is why its kappa is higher. But it finds few of them, and it sometimes reports a difference on a consistent card, for example from the licence files of Python packages vendored in the repo.
- **What a difference means.** Treat `inconsistent` as "look here", not as "wrong".
- **The labels.** The held-out labels are not an independent audit, because the author of the tool made them. "Agreement" means agreement with a set of labels, not accuracy: the DPI calls its own labels self-reported and best-effort.

Details, confusion matrices, deviations from the pre-registration and the limits: [RESULTS.md sections 1, 2 and 4](https://github.com/moelsaka01/datasetvet/blob/main/RESULTS.md#1-licence-status-held-out-evaluation-pre-registered).

## Method and limits

- **Deterministic, no AI in any decision.** Licence detection is a built-in matcher against SPDX licence list fingerprints (no licence text is shipped), or optionally the [ScanCode toolkit](https://github.com/aboutcode-org/scancode-toolkit). Every report names the scanner and version.
- **Facts about one revision.** Everything is read at a pinned commit, with the time of the check in the report. Links die and cards change.
- **Not covered:** licences that are not on the SPDX list (Llama, OpenRAIL, custom terms) and paraphrases ("for research use only") give `unknown`, never a guess. Gated datasets are checked on their card only; the tool never accepts terms for you.
- **PII patterns** are email and international phone patterns. The report says "pattern matches", not "contains personal data", and makes no recall claim.
- **Contradiction recall is low:** 2 of 6 contradictions found on the held-out set, 9 of 57 against the DPI key. "No contradiction found" does not mean there is none. Improving this is first on the v0.2 list.
- **The author labelled the held-out set, starting from AI drafts.** The author changed 12 of the 120 AI-drafted statuses.
- The full list of limits is in [RESULTS.md section 4](https://github.com/moelsaka01/datasetvet/blob/main/RESULTS.md#4-limits); the design and rules are in [PLAN.md](https://github.com/moelsaka01/datasetvet/blob/main/PLAN.md).

## Very large repos

A repo with 100,000 or more files is slow to read in full. datasetvet says so before reading any data: the file count, an estimated time, and how to run a sampled scan. In a terminal it asks first; `--yes`, CI and the GitHub Action proceed, and the report's scan line always says it was a large repo. Measured on one repo of 389,052 files (146,744 of them data files): listing the files took about 4 minutes, a sampled read about 5 minutes, and a full read an estimated 85 minutes, so expect about an hour for a full read of a repo with 100,000 data files ([RESULTS.md section 3](https://github.com/moelsaka01/datasetvet/blob/main/RESULTS.md#time-for-a-very-large-repo-measured-2026-11-22)). For minutes instead of an hour:

```powershell
datasetvet check hf:org/big-dataset --max-scan-bytes 100MB --sample-rows 10000 --max-download-bytes 100MB
```

## Use it in CI

The repo ships a GitHub Action that checks a dataset on every push, on a schedule, or on demand, and writes the report to the job summary:

```yaml
- uses: moelsaka01/datasetvet@v0
  with:
    dataset: hf:org/name
    fail-on: "inconsistent dead"   # optional: fail the job on these statuses
```

`fail-on` takes statuses (`inconsistent`, `missing`, `invalid`, `dead`, `unreachable`, `restricted`, `found`); with it empty the Action only writes the report. A complete workflow is in [`examples/workflow.yml`](https://github.com/moelsaka01/datasetvet/blob/main/examples/workflow.yml). The same switch works on the command line: `datasetvet check hf:org/name --md report.md --fail-on inconsistent` exits with status 3 when a result has that status.

## Options and install notes

- `datasetvet check --help` lists every option (`--no-data`, `--no-links`, `--scanner`, `--full`, `--phone-region`, ...).
- The optional ScanCode scanner: `pip install "datasetvet[scan]"`. On Windows it needs a short venv path and PowerShell; the steps are in [docs/INSTALL.md](https://github.com/moelsaka01/datasetvet/blob/main/docs/INSTALL.md).
- Python 3.11 or newer.

## What it will not do

- **Facts only, not legal advice.** Licence statuses are only *consistent*, *inconsistent*, *missing* or *unknown*. It never says a dataset is "safe to use" or that a use is permitted. It does not judge how a dataset may be used.
- **No AI in any decision.** An optional AI summary is not part of the tool.
- **No accuracy claim without a number.** The numbers above are the measurements; the limits next to them are part of the result.

## Licence

MIT. See [LICENSE](https://github.com/moelsaka01/datasetvet/blob/main/LICENSE). Built with Claude Code; the build history, including every model and decision, is in [BUILD_LOG.md](https://github.com/moelsaka01/datasetvet/blob/main/BUILD_LOG.md).
