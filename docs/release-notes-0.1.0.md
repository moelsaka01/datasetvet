First release. `pip install datasetvet`, then `datasetvet check hf:org/name`.

datasetvet checks a Hugging Face dataset and writes a report of verifiable facts, each with an evidence link pinned to a commit:
- whether the README text, the repo's licence files and the sources the card points to agree with the card's licence;
- dead links and `data_files` paths that match no file;
- exact duplicate rows within a split and train/test leakage;
- empty rows and PII-pattern matches.

No AI in any decision. Facts only, not legal advice. There is also a GitHub Action (`moelsaka01/datasetvet@v0`).

**What it found in the 500 most-downloaded HF datasets** ([RESULTS.md](https://github.com/moelsaka01/datasetvet/blob/main/RESULTS.md), 95% intervals):
- 36.6% (182 of 497) state no licence in the card.
- Of the 315 that state one, 132 have it confirmed by another place, and 20 (6.3%) have a source naming a different licence.
- 20.5% of the 356 datasets whose rows were read have exact duplicate rows within a split; 6.7% share inputs between splits (lower bounds for sampled datasets).
- 18 of the 172 datasets with links have a dead one.

**How accurate the licence status is:**
- On a pre-registered held-out set (64 rows; AI-assisted labels, every row reviewed and corrected by the author against the pinned cards), datasetvet met the kappa (0.63) and abstention (9.4%) targets and beat ScanCode alone.
- **It did not beat the HF `license:` tag alone**: 52 against 58 rows agree (p = 0.11). Against the Data Provenance Initiative's human audit it ties with the tag.
- It finds few contradictions: 2 of 6 on the held-out set.
- Improving that is first on the v0.2 list. Limits and deviations are in RESULTS.md sections 1 and 4.
