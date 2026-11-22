# Launch posts (drafts)

Drafts only. **Nothing here has been posted**; the owner posts them. Before posting: replace `<REPO>` with the GitHub URL, `<PYPI>` with the PyPI URL, and check each number against [RESULTS.md](RESULTS.md) (every figure below is copied from it, with its section).

## The finding to lead with

Lead with what the scan found, not with the tool. Three numbers carry the story; all are from the launch scan of the 500 most-downloaded Hugging Face datasets (list frozen 2026-11-19, anonymous, built-in matcher; RESULTS.md section 2, headline table):

| number | how it is counted |
|---|---|
| **40.1%** state no licence in the card (200 of 499) | the card's `license` is absent, empty or `unknown` |
| **12.4%** of the 299 that do have a comparison that differs (37; 9.1–16.6%) | the card's licence differs from the README text, a repo licence file or a source the card points to |
| **20.5%** of the 356 datasets whose rows were read have exact duplicate rows inside a split (73; 16.6–25.0%) | a lower bound for the sampled ones; 6.7% share inputs between two splits (24; 4.6–9.8%) |

Say these every time, because the numbers are easy to over-read:

- "differs" is a fact to look at, not a verdict. A source repo's `LICENSE` often covers its code while the card names the data licence. Against the Data Provenance Initiative's audit the `inconsistent` status has 37% precision and 28% recall (RESULTS.md section 1), so it is a pointer, not a finding of wrongdoing.
- Agreement with that audit is 76.0% on the rows where the tool gave an answer (95% CI 69.3–81.6%), and it answered `unknown` on 25.3%. It measures agreement with a best-effort human audit, not truth.
- Data-health numbers come from a laptop-sized launch scan (full scan up to 100 MB, else a 10,000-row sample).
- Do not single out individual datasets or their maintainers in a post. The per-dataset table is in the repo for anyone who wants to check their own.
- Say it is built with Claude Code if asked; the build log is public.

---

## r/MachineLearning (flair: Project)

**Title:** 40% of the 500 most-downloaded Hugging Face datasets state no licence in their card. I wrote a CLI to check this for any dataset [P]

**Body:**

I ran a checker over the 500 most-downloaded datasets on the Hub (list frozen 2026-11-19).

- 200 of 499 (40.1%) state no licence in the card.
- Of the 299 that do, 37 (12.4%; 95% CI 9.1–16.6%) have a README, repo licence file or linked source that names a different licence. Often this is a source repo whose `LICENSE` covers its code, not the data; the tool reports both licences and says they differ, nothing more.
- Of the 356 datasets whose rows I could read, 73 (20.5%; 16.6–25.0%) have exact duplicate rows inside a split, and 24 (6.7%) share inputs between train and test.
- 16 of the 166 that state links have a dead one.

How it works: `datasetvet check hf:org/name` reads the card, the licence files and the sources it points to, then streams the data. It produces facts with an evidence link pinned to a commit: four licence statuses (consistent / inconsistent / missing / unknown), dead links, duplicates, cross-split leakage, empty rows, PII-pattern matches. No AI in any decision; it never says a dataset is "safe", and it is not legal advice.

How accurate: I scored the licence statuses against the Data Provenance Initiative's hand-audited labels (245 held-out datasets). On rows where it gave an answer it agrees 76.0% of the time (69.3–81.6%); it says `unknown` on 25.3%. `inconsistent` has 37% precision and 28% recall against that key, mostly because the key records one licence per dataset while the tool compares each source. The key is itself self-reported and best-effort, so this is agreement, not accuracy. Everything, including the limits and the disagreement audit, is in RESULTS.md.

Limits you should know: the data-health numbers come from a laptop-sized scan (full scan up to 100 MB, otherwise a 10,000-row sample), so they are lower bounds; 103 of the 500 could not be checked for data (gated, no Parquet conversion, or the viewer is off); licences that are not on the SPDX list give `unknown`.

Code (MIT), results and per-dataset CSV: <REPO>. `pip install datasetvet` (<PYPI>). There is also a GitHub Action that writes the report to the job summary.

Happy to hear what other checks would be useful, and where the licence comparison is wrong.

---

## r/datasets

**Title:** I checked the licences, links and data of the 500 most-downloaded Hugging Face datasets (open data + free tool)

**Body:**

Per-dataset results for the top 500 Hugging Face datasets (frozen 2026-11-19) are in a CSV: card licence, whether the README/licence files/sources agree with it, dead links, duplicate rows, train/test leakage, empty rows, PII-pattern matches. Facts only; no dataset is graded.

Headlines: 40.1% (200 of 499) state no licence in the card; of the 299 that do, 12.4% (37) have a source that names a different one; 20.5% of the 356 datasets whose rows I read have exact duplicate rows within a split.

The CSV, the method and the limits (it is a laptop-sized scan, so the data numbers are lower bounds) are in the repo: <REPO>. The same checks run on any dataset with `pip install datasetvet` and `datasetvet check hf:org/name`. Not legal advice.

---

## X

Post 1 (leads with the finding; X counts a link as 23 characters, so this fits in 280 with the real URL):

> 40% of the 500 most-downloaded Hugging Face datasets state no licence in their card. Of the 299 that do, 12% have a README, LICENSE file or source naming a different one. I built a free CLI that checks this for any dataset. Facts only, not legal advice. <REPO>

Reply 2:

> 20.5% of the 356 datasets whose rows I could read have exact duplicate rows inside a split; 6.7% share inputs between train and test. These are lower bounds (laptop-sized scan, sampled above 100 MB).

Reply 3:

> The licence check agrees 76% (CI 69–82%) with a hand-audited key on rows it answers, and says "unknown" on 25%. "Different" is a pointer, not a verdict: precision on it is 37%. Method, limits and the disagreement audit: <REPO>/blob/main/RESULTS.md

Attach `docs/demo/demo.gif` to post 1.

---

## LinkedIn

**40% of the 500 most-downloaded Hugging Face datasets state no licence in their card.**

Before you train on a dataset you want to know what its card says, what its source says, whether the links still work, and what is in the data. I built a free command-line tool, datasetvet, that checks those things for any Hugging Face dataset and writes a report of verifiable facts. Then I ran it on the top 500 by downloads.

What it found (frozen 2026-11-19):
- 200 of 499 cards state no licence.
- Of the 299 that do, 37 (12.4%) have a README, licence file or linked source that names a different licence. Often that is a source repo whose LICENSE covers its code; the report shows both licences and says they differ, nothing more.
- Of 356 datasets whose rows I could read, 73 (20.5%) have exact duplicate rows inside a split and 24 (6.7%) share inputs between train and test.

How far to trust it: against a human audit by the Data Provenance Initiative the tool agrees on 76% of the rows it answers (95% CI 69–82%) and says "unknown" on 25%. The audit is itself best-effort, so that is agreement, not accuracy. The data numbers come from a laptop-sized scan and are lower bounds.

No AI in any decision, no "safe to use" verdicts, and it is not legal advice: facts with evidence links, that is all. MIT licensed, with a GitHub Action for CI. Method, limits and per-dataset results: <REPO>

---

## Hugging Face community post

**Title:** What the top 500 datasets say about their licences, and a tool to check yours

**Body:**

If you maintain a dataset on the Hub, here is what a scan of the 500 most-downloaded datasets (frozen 2026-11-19) found, and how to check your own.

- 40.1% (200 of 499) have no licence in the card metadata. If yours does not, adding the `license:` field is the single most useful fix.
- Of the 299 that state one, 12.4% have a README, repo licence file or linked source that names a different licence. Often a source repo's `LICENSE` covers code while the card names the data licence; saying which covers what in the card removes the doubt.
- 9.6% of the datasets with links have a dead one (16 of 166).
- 20.5% of the 356 datasets whose rows I read have exact duplicate rows inside a split; 6.7% share inputs between splits.

To check your own dataset:

```
pip install datasetvet
datasetvet check hf:your-org/your-dataset
```

It reads the card, licence files and sources, then streams the data, and prints facts with evidence links. There is a GitHub Action too, if you want it in CI. It uses no AI, gives no "safe to use" verdicts and is not legal advice. Numbers are a laptop-sized scan, so data-health counts are lower bounds; method, limits and accuracy (76% agreement with a human audit on the rows it answers) are in RESULTS.md: <REPO>

Feedback welcome, especially where a licence comparison is wrong.

---

## After the audit is labelled

Once the owner's disagreement labels are in RESULTS.md ("Human audit"), add one line to the r/MachineLearning and LinkedIn posts: of the 60 sampled disagreements, how many were datasetvet's fault, the key's, changed since the audit, or ambiguous. Do not post before that line is in if the `inconsistent` precision is the main point of a comment thread.
