# datasetvet

**Before you train on it, check it.**

> **Status: Phase 3 of 5.** Card, licence consistency, provenance, link and data-health checks work for Hugging Face datasets. Accuracy has not been measured yet (Phase 4). The design is in [PLAN.md](PLAN.md), the build history in [BUILD_LOG.md](BUILD_LOG.md), and install notes (including the optional ScanCode extra on Windows) in [docs/INSTALL.md](docs/INSTALL.md).

```powershell
pip install -e .
datasetvet check hf:stanfordnlp/imdb --json report.json
```

It uses free endpoints only. If you are logged in with `hf auth login` (or set `HF_TOKEN`), your token raises the Hub's rate limits. It is sent only to Hugging Face hosts and is never printed or stored.

datasetvet will be a free, local CLI that checks a dataset (Hugging Face first) and writes a report card of **verifiable facts**:

- **Card:** licence field present and a valid SPDX id, required metadata, citation, stated source.
- **Licence consistency:** the card's licence compared with the README text, the repo's licence files, and the licence of the source it points to.
- **Provenance:** the licences of declared parent datasets, side by side.
- **Links:** dead source URLs and missing files.
- **Data health:** exact duplicates within splits, leakage across train/test, empty rows, files that could not be read as rows, label balance, PII-pattern matches. A full scan by default; large datasets are sampled, and the report always says which.

Each fact comes with an evidence link pinned to a commit.

**Very large repos take time.** Measured on one repo with 389,052 files (146,744 of them data files, [RESULTS.md section 2](RESULTS.md)): listing the files took about 4 minutes (under a minute per 100,000 files, with a Hugging Face token), a sampled read about 5 minutes, and a full read an estimated 85 minutes. Expect about an hour for a full read of a repo with 100,000 data files; use a sampled scan (`--max-scan-bytes`, `--sample-rows`) to keep it to minutes.

## What it will not do

- **No legal judgements.** Licence statuses are only *consistent*, *inconsistent*, *missing* or *unknown*. It never says a dataset is "safe to use". **This is not legal advice.**
- **No AI in any decision.** Licence detection is deterministic: a built-in matcher against the official SPDX licence texts, or optionally the [ScanCode toolkit](https://github.com/aboutcode-org/scancode-toolkit) (`pip install "datasetvet[scan]"`). Every report names the scanner it used. An AI summary may be added later as an optional extra; it will be off by default and clearly labelled.
- **No accuracy claims without measurement.** Before launch, it will be scored against the Data Provenance Initiative's hand-audited licences, with a confusion matrix for each scanner ([PLAN.md section 8](PLAN.md#8-accuracy-evaluation)).

## Licence

MIT. See [LICENSE](LICENSE).
