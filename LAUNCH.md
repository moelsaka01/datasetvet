# Launch posts (drafts)

Drafts only. **Nothing here has been posted**; the owner posts them. Before posting: replace `<REPO>` with the GitHub URL, `<PYPI>` with the PyPI URL, and check each number against [RESULTS.md](RESULTS.md) (every figure below is copied from it, with its section).

## The finding to lead with

Lead with what the scan found, not with the tool. All numbers are from the launch scan of the 500 most-downloaded Hugging Face datasets (list frozen 2026-11-19, each read at its pinned commit, anonymous, built-in matcher, v2 rules; RESULTS.md headline and section 3):

| number | how it is counted |
|---|---|
| **36.6%** state no licence in the card (182 of 497; 32.5–40.9%) | the card's `license` is absent, empty or `unknown` |
| **20.5%** of the 356 datasets whose rows were read have exact duplicate rows inside a split (73; 16.6–25.0%) | a lower bound for the sampled ones |
| **6.7%** share inputs between two splits, i.e. train/test leakage (24 of 356; 4.6–9.8%) | a lower bound for the sampled ones |
| **10.5%** of the datasets with links checked have a dead one (18 of 172; 6.7–15.9%) | dead URLs and card `data_files` paths that match no file |
| of the 315 cards that state a licence: **41.9%** confirmed by another place (132), **6.3%** with a README, licence file or source naming a different licence (20; 4.1–9.6%) | none of this is visible from the `license:` tag |

Say these every time, because the numbers are easy to over-read:

- **The licence status is not more accurate than the tag.** On a pre-registered held-out set, the HF `license:` tag alone agreed with the labels on 58 of 64 rows and datasetvet on 52 (2 rows only datasetvet got right, 8 only the tag; p = 0.11). The goal was missed on that part. The tool's value is in what the tag can't show (confirming or contradicting sources, dead links, duplicates, leakage), not in a better consistent/not label.
- **"Differs" is a fact to look at, not a verdict.** datasetvet found 2 of the 6 contradictions in the held-out set and 9 of 57 against the Data Provenance Initiative's audit, so it misses most contradictions, and some differences it reports are not contradictions. RESULTS.md section 1 lists the causes.
- **Who made the labels.** The held-out labels are AI-assisted labels, every row reviewed and corrected by the author against the pinned cards. Do not call them an independent human audit. The Data Provenance Initiative's audit is the independent human key; against it, datasetvet agrees on 177 of 245 rows, and the tag alone on 179. Those rows are no longer blind.
- **Data-health numbers** come from a laptop-sized launch scan (full scan up to 100 MB, else a 10,000-row sample).
- **The first scan over-counted cards with no licence:** in 18 very large repos it did not find the README. If anyone quotes the earlier figure, the corrected one is 36.6%; RESULTS.md section 3 says what happened.
- Do not single out individual datasets or their maintainers in a post. The per-dataset table is in the repo for anyone who wants to check their own.
- Say it is built with Claude Code if asked; the build log is public.

---

## r/MachineLearning (flair: Project)

**Title:** 37% of the 500 most-downloaded Hugging Face datasets state no licence in their card, and 1 in 5 of those I could read have duplicate rows. I wrote a CLI that checks any dataset [P]

**Body:**

I ran a checker over the 500 most-downloaded datasets on the Hub (list frozen 2026-11-19, each read at its pinned commit).

- 182 of 497 (36.6%; 95% CI 32.5–40.9%) state no licence in the card.
- Of the 315 that do, 132 have the same licence confirmed somewhere else (README text, a licence file, the linked source repo). 20 (6.3%) have a README, licence file or source that names a different licence. That is a difference to look at, not a verdict.
- Of the 356 datasets whose rows I could read, 73 (20.5%; 16.6–25.0%) have exact duplicate rows inside a split, and 24 (6.7%) share inputs between splits.
- 18 of the 172 with links have a dead one.

How it works: `datasetvet check hf:org/name` reads the card, the licence files and the sources it points to, then streams the data. It produces facts with an evidence link pinned to a commit: four licence statuses (consistent / inconsistent / missing / unknown), dead links, duplicates, cross-split leakage, empty rows, PII-pattern matches. No AI in any decision; it never says a dataset is "safe", and it is not legal advice.

How accurate the licence status is, honestly: I pre-registered a goal and scored it on 64 held-out datasets. It met the kappa and abstention targets and beat ScanCode alone, but **it did not beat simply reading the HF licence tag**. The tag alone agreed with the labels on 58 of 64 rows, datasetvet on 52. Against the Data Provenance Initiative's hand audit it is a tie (177 against 179 of 245 rows). It finds only some contradictions (2 of 6 on the held-out set). So the licence check is useful for showing *where* the licence is confirmed or contradicted, not as a better yes/no. The held-out labels are mine: AI-assisted, with every row reviewed and corrected by me against the pinned cards. Everything, including the misses and the deviations from the pre-registration, is in RESULTS.md.

Limits you should know: the data-health numbers come from a laptop-sized scan (full scan up to 100 MB, otherwise a 10,000-row sample), so they are lower bounds; 103 of the 500 could not be checked for data (gated, no Parquet conversion, or the viewer is off); licences that are not on the SPDX list give `unknown`.

Code (MIT), results and per-dataset CSV: <REPO>. `pip install datasetvet` (<PYPI>). There is also a GitHub Action that writes the report to the job summary.

Happy to hear what other checks would be useful, and where the licence comparison is wrong.

---

## r/datasets

**Title:** I checked the licences, links and data of the 500 most-downloaded Hugging Face datasets (open data + free tool)

**Body:**

Per-dataset results for the top 500 Hugging Face datasets (frozen 2026-11-19) are in a CSV: card licence, whether the README/licence files/sources confirm or contradict it, dead links, duplicate rows, train/test leakage, empty rows, PII-pattern matches. Facts only; no dataset is graded.

Headlines: 36.6% (182 of 497) state no licence in the card; 20.5% of the 356 datasets whose rows I read have exact duplicate rows within a split, and 6.7% share inputs between splits; 10.5% of those with links have a dead one.

The CSV, the method and the limits (it is a laptop-sized scan, so the data numbers are lower bounds; the licence status is not more accurate than the HF tag as a yes/no) are in the repo: <REPO>. The same checks run on any dataset with `pip install datasetvet` and `datasetvet check hf:org/name`. Not legal advice.

---

## X

Post 1 (leads with the finding; X counts a link as 23 characters, so this fits in 280 with the real URL):

> 37% of the 500 most-downloaded Hugging Face datasets state no licence in their card. 1 in 5 of those I could read have duplicate rows inside a split. I built a free CLI that checks licence sources, dead links, duplicates and leakage. Not legal advice. <REPO>

Reply 2:

> 20.5% of the 356 datasets whose rows I read have exact duplicate rows inside a split; 6.7% share inputs between splits. Lower bounds (laptop-sized scan, sampled above 100 MB). 18 of 172 with links have a dead one.

Reply 3:

> Honest accuracy: on a pre-registered held-out set its licence status did NOT beat just reading the HF licence tag (52 vs 58 of 64 agree). Its value is showing where a licence is confirmed or contradicted, plus the data checks. Misses and method: <REPO>/blob/main/RESULTS.md

Attach `docs/demo/demo.gif` to post 1.

---

## LinkedIn

**37% of the 500 most-downloaded Hugging Face datasets state no licence in their card.**

Before you train on a dataset you want to know what its card says, whether its sources say the same, whether the links still work, and what is in the data. I built a free command-line tool, datasetvet, that checks those things for any Hugging Face dataset and writes a report of verifiable facts. Then I ran it on the top 500 by downloads.

What it found (frozen 2026-11-19):
- 182 of 497 cards state no licence.
- Of the 315 that do, 132 have the licence confirmed by another place, and 20 have a README, licence file or linked source naming a different one. The report shows both and says they differ, nothing more.
- Of 356 datasets whose rows I could read, 73 (20.5%) have exact duplicate rows inside a split and 24 (6.7%) share inputs between train and test.
- 18 of the 172 with links have a dead one.

How far to trust the licence part: I pre-registered a goal and tested it on a held-out set. It met two targets and beat ScanCode, but as a single yes/no it was not more accurate than reading the Hugging Face licence tag (52 against 58 of 64 rows agree). It finds only some contradictions. The labels are mine (AI-assisted, every row reviewed and corrected by me), so they are not an independent audit; against the Data Provenance Initiative's human audit it ties with the tag. I'm publishing the miss along with everything else.

No AI in any decision, no "safe to use" verdicts, and it is not legal advice: facts with evidence links, that is all. MIT licensed, with a GitHub Action for CI. Method, limits and per-dataset results: <REPO>

---

## Hugging Face community post

**Title:** What the top 500 datasets say about their licences and data, and a tool to check yours

**Body:**

If you maintain a dataset on the Hub, here is what a scan of the 500 most-downloaded datasets (frozen 2026-11-19) found, and how to check your own.

- 36.6% (182 of 497) have no licence in the card metadata. If yours does not, adding the `license:` field is the single most useful fix.
- Of the 315 that state one, 6.3% (20) have a README, repo licence file or linked source that names a different licence. Often a source repo's `LICENSE` covers code while the card names the data licence; saying which covers what in the card removes the doubt.
- 10.5% of the datasets with links have a dead one (18 of 172), most often a `data_files` path in the card that matches no file.
- 20.5% of the 356 datasets whose rows I read have exact duplicate rows inside a split; 6.7% share inputs between splits.

To check your own dataset:

```
pip install datasetvet
datasetvet check hf:your-org/your-dataset
```

It reads the card, licence files and sources, then streams the data, and prints facts with evidence links. There is a GitHub Action too, if you want it in CI. It uses no AI, gives no "safe to use" verdicts and is not legal advice. The numbers are from a laptop-sized scan, so data-health counts are lower bounds. As a yes/no, the licence status is not more accurate than your `license:` tag; it shows where the tag is confirmed or contradicted. Method, limits and the accuracy evaluation are in RESULTS.md: <REPO>

Feedback welcome, especially where a licence comparison is wrong.

---

## Before posting

- The two Phase 4 disagreement samples (RESULTS.md section 5) are still unlabelled. They concern the superseded v1 rules, so they are not needed for these posts.
- If a comment thread is about licence accuracy, link RESULTS.md section 1 and the v0.2 list (PLAN.md §11) rather than arguing the numbers.
