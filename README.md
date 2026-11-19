# datasetdoctor

**Before you train on it, check it.**

> **Status: planning (Phase 1 of 5). Nothing works yet.** The design is in [PLAN.md](PLAN.md) and the build history is in [BUILD_LOG.md](BUILD_LOG.md). The name is a working name.

datasetdoctor will be a free, local CLI that checks a dataset (Hugging Face first) and writes a report card of **verifiable facts**:

- **Card:** licence field present and a valid SPDX id, required metadata, citation, stated source.
- **Licence consistency:** the card's licence compared with the README text, the repo's licence files, and the licence of the source it points to.
- **Provenance:** the licences of declared parent datasets, side by side.
- **Links:** dead source URLs and missing files.
- **Data health:** exact duplicates within splits, leakage across train/test, empty or corrupt rows, label balance, PII-pattern matches. A full scan by default; large datasets are sampled, and the report always says which.

Each fact comes with an evidence link pinned to a commit.

## What it will not do

- **No legal judgements.** Licence statuses are only *consistent*, *inconsistent*, *missing* or *unknown*. It never says a dataset is "safe to use". **This is not legal advice.**
- **No AI in any decision.** Licence detection uses a deterministic scanner ([ScanCode toolkit](https://github.com/aboutcode-org/scancode-toolkit)). An AI summary may be added later as an optional extra; it will be off by default and clearly labelled.
- **No accuracy claims without measurement.** Before launch, it will be scored against the Data Provenance Initiative's hand-audited licences, with a confusion matrix ([PLAN.md section 8](PLAN.md#8-accuracy-evaluation)).

## Licence

MIT. See [LICENSE](LICENSE).
