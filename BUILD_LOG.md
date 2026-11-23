# Build log

One entry per phase: the model and effort used, what was decided and why, what was measured, and what is still open. Newest last.

| phase | model | effort | status |
|---|---|---|---|
| 1 Planning | Opus 5.5 | high | done 2026-11-19 |
| 2 Core checks (no licences) | Sonnet 5.5 planned; run on Opus 5.5 | medium planned | done 2026-11-19 |
| 3 Licence + provenance | Opus 5.5 | high | done 2026-11-19 |
| 4 Accuracy eval + launch scan | Opus 5.5 | high | done 2026-11-21 |
| 4.5 Fixes from the launch scan + rescan | Sonnet 5.5 (closing steps on Opus 5.5) | high | done 2026-11-22; history rewrite pending |
| 5 Polish, Action, README, launch | Sonnet 5.5 | medium | built 2026-11-22; the Opus review fixes and the human audit table wait for the owner's inputs; nothing pushed or published |
| 5.5 Close the gap to the human audit (v2 rules, held-out eval) | Opus 5.5 | high | done 2026-11-23: goal missed (beats ScanCode, not the HF tag alone); v2 launch re-run; nothing pushed |

---

## Phase 1: planning (2026-11-19, Opus 5.5, high effort)

Run in one Claude Code session (desktop app) on the owner's Windows 11 laptop, Python 3.12.10, on a Claude Pro plan. No paid APIs, no tokens used: every probe was anonymous.

### Decisions

| decision | choice | why |
|---|---|---|
| Language | Python ≥ 3.11 | `huggingface_hub` (built-in 429 handling), ScanCode is a Python library, `pyarrow`/`duckdb` Windows wheels; `pyarrow` 26 needs 3.11 |
| Licence scanner | ScanCode toolkit, as the optional `[scan]` extra | only option that detects licence *notices inside READMEs and web pages*, not just LICENSE files; deterministic, gives scores and lines. askalono: full texts only, last release 2024-10. licensee: needs Ruby |
| Licence statuses | consistent / inconsistent / missing / unknown only | design rule 1 |
| Licence properties | SPDX flags + Creative Commons BY/SA/NC/ND elements only | SPDX data does not publish NC/SA for non-CC licences; showing nothing beats interpreting |
| Full-scan limit | 5 GB of Parquet, then a deterministic row-group sample of up to 1M rows | 5 GB is ~7 min of download at 100 Mbit/s; above it a default run could take hours |
| Row identity | canonical encoding + xxh3_128, two hashes (`row`, `input` without labels) | exact duplicates, plus "same input, different label" leakage |
| Duplicate counting | DuckDB on disk | stays within laptop RAM for large datasets |
| Answer key | DPI `data_summaries` (GitHub, Apache-2.0), not their HF datasets | the HF datasets are filtered training data without licence tags; the GitHub JSON has expert licences + what the card said at audit time |
| Badge | local SVG, factual text, no green | green reads as "safe" |
| Project licence | MIT | matches the owner's other projects (tierview, honest-ml, honest-tests are MIT) |
| Name | **`datasetvet`** (renamed from the working name `datasetdoctor` by the owner after Phase 1) | `datasetdoctor` was free on PyPI/npm but crowded on GitHub (8 repos, `dataset-doctor` taken on PyPI); `datasetvet` is free on PyPI, npm and GitHub (re-checked 2026-11-19) |

### Measured

- **Names:** `datasetdoctor` free on PyPI and npm, 8 GitHub repos use it; `dataset-doctor` taken on PyPI. Free everywhere with 0 GitHub repos: `datasetvet`, `cardvet`, `datapreflight`, `trainvet`.
- **HF rate limits** from live headers: API `q=500;w=300`, resolvers `q=3000;w=300` (anonymous). Docs: free account 1,000 / 5,000 per 5 min. The Dataset Viewer sent no rate-limit headers.
- **HF endpoints** confirmed working: dataset list with cursor pagination, dataset info (`cardData`, `siblings`, `sha`), `/parquet` (Hub and Dataset Viewer), `/size`, `/is-valid`, raw README via `resolve`.
- **Scale:** `HuggingFaceFW/fineweb-edu` has 2,410 Parquet files, 4,523 GB.
- **DPI key:** 109 files, 3,718 entries, 3,490 HF-linked, 804 unique HF repos, 3,342 with a named verifier, 3,133 with the audit-time HF YAML licence.
- **ScanCode on Windows:**
  - failed to install under a long path (MAX_PATH);
  - at a short path it installed in 116 s, to a 637 MB venv;
  - it then crashed on import with `pluggy` 1.7.0, and segfaulted under Git Bash (Git's libmagic);
  - with `pluggy<1.6` + `typecode-libmagic`, run from PowerShell, it detected CC-BY-NC-4.0 / MIT / CC-BY-SA-4.0 correctly on 3 samples, with 3.6–5.7 s index load and <0.1 s per file;
  - the test venvs were deleted afterwards.

### Corrections to the brief

- `Commercially-Verified-Licenses` is a DPI **dataset** (filtered training data), not a checking tool.
- No licence-compliance tool named Calibra was found. The Calibra that exists is robot-dataset observability.
- "Licence properties via SPDX data" is narrower than hoped: SPDX publishes OSI/FSF/deprecated flags, not non-commercial or share-alike. See PLAN.md §5.2.

### Not done / open

- No GitHub repo created, nothing pushed.
- SPDX licence-list data's own licence not verified (GitHub reports NOASSERTION); task 3.3.
- Dataset Viewer rate limits unknown; measured in Phase 4.
- Launch-scan bandwidth unknown until task 4.1 sums the top-500 sizes.

---

## Phase 2: core checks without licences (2026-11-19)

**Model:** planned Sonnet 5.5 at medium effort. This session actually ran on **Opus 5.5**, so the log records that rather than the planned model.

**Setup:** run in one Claude Code session (desktop app), Windows 11, Python 3.12.10. The folder had been renamed `datasetdoctor` → `datasetvet` and the old `.venv` deleted, so the venv was recreated (`py -3.12 -m venv .venv`, `pip install -e ".[dev]"`).

**Tokens:** no HF token was present (no `HF_TOKEN`, no login file), so every live call was anonymous. The code reads a token only through `huggingface_hub.get_token()`, sends it only to `huggingface.co` / `datasets-server.huggingface.co` (on every redirect hop), and never logs, caches or reports it. Reports show only `authenticated: yes/no`. Only free endpoints were used.

### Licence scanner: default vs extra (checked before coding)

- The plan had **no default licence-text scanner**. ScanCode is the optional `[scan]` extra (652 MB venv).
- With the core install, licence evidence is only:
  - the card's YAML `license`;
  - GitHub's detected licence, when `GITHUB_TOKEN` is set.
- Every text-based claim is `unknown (scanner not installed)`. PLAN §4 now says this explicitly.
- §8 did not say which configuration the accuracy evaluation runs. It now runs `default` and `scancode` separately, on the same key, split and frozen config, with one confusion matrix and set of metrics each, never pooled. Tasks 4.5/4.6 are updated to match.
- Open for the owner: whether the core install should get a small built-in matcher (PLAN §12).

### Built (tasks 2.1–2.13)

| task | files | state |
|---|---|---|
| 2.1 models, closed status enums, JSON round-trip | `model.py` | done; a status outside its family's enum raises |
| 2.2 HTTP layer | `http.py` | done. RateLimit/RateLimit-Policy limiter paces a bucket below 20% of q; 429 sleeps `Retry-After` or `t` (3 retries); 5xx/connection retries with backoff; on-disk cache for revision-pinned GETs; manual redirects; UA has no personal data |
| 2.3 adapter protocol + registry | `hubs/base.py` | done; interface changes listed in PLAN §6 |
| 2.4 HF adapter | `hubs/huggingface.py`, `tests/fixtures/hf/` | done; recorded fixtures for imdb, gated `cais/hle`, viewer-disabled `nvidia/simready-assets` (front matter only, no card prose); `record.py` re-records them; one `network` test |
| 2.5 card check | `checks/card.py` | done except HF-id/SPDX validity (task 3.1) |
| 2.6 link check | `checks/links.py` | done; status table reproduced against a local server |
| 2.7 row hashing | `checks/health/rowhash.py` | done |
| 2.8 scan planner + reader | `checks/health/scan.py` | done; sampling detail in PLAN §5.5 |
| 2.9 duplicates + leakage | `checks/health/duplicates.py` | done; DuckDB on disk |
| 2.10 empty, corrupt, labels | `empty.py`, `labels.py`, `runner.py` | done |
| 2.11 PII patterns | `checks/health/pii.py` | done; masked examples |
| 2.12 JSON + terminal, CLI `check` | `report/`, `cli.py`, `pipeline.py`, `config.py` | done |
| 2.13 CI | `.github/workflows/ci.yml` | **written, not run.** Nothing is pushed. The matrix covers Windows and Ubuntu on 3.11–3.13, but only 3.12 on Windows was run locally |

**Checks:**
- `pytest`: 125 offline tests pass in about 28 s, plus 1 live test with `-m network`.
- `ruff check src tests`: clean.
- `mypy src`: clean.

### Live runs (anonymous, 2026-11-19)

| dataset | why | result | data scan |
|---|---|---|---|
| `stanfordnlp/imdb` | plan's target; 3 splits, ClassLabel | duplicates found (test 199, train 96, unsupervised 493 extra copies); test∩train 123 shared inputs, 0 with different labels; 89 text values match the email pattern; 2 links ok | **Full scan**, 100,000 rows, 83.4 MB, 14.0 s scan (23 s wall without cache) |
| `stanfordnlp/imdb` `--max-scan-bytes 30MB --sample-rows 20000 --seed 1` | sampled path | header `Sampled: 20,000 of 100,000 rows (seed 1)`; counts labelled "at least"; same sample on re-run | 8.6 s; still 83.4 MB downloaded (one file per split) |
| `cornell-movie-review-data/rotten_tomatoes` | small, clean | card `license: unknown` → licence field `missing`; no duplicates, no leakage, no PII matches; 3 links ok | **Full scan**, 10,662 rows, 0.9 MB, 3.2 s |
| `dair-ai/emotion` | 2 configs | `split/train` 1 duplicate, `unsplit/train` 686; leakage test∩train 11, test∩val 3, train∩val 5, each with different labels | **Full scan**, 436,809 rows, 28.2 MB, 20.8 s |
| `cais/hle` | gated (auto) | card readable anonymously; data `not checked` (gated, terms never accepted); 3 stated links ok | not checked |
| `nvidia/simready-assets` | Dataset Viewer disabled | data `not checked`: viewer disabled and no `configs`, so nothing states which files are data | not checked |
| `nobody-xyz/does-not-exist-123` | error path | exit 1, "not found on the Hugging Face Hub, or private …" | – |

**Throughput on this laptop:**
- About 7,000 rows/s (6 MB/s) for IMDB's long reviews, and about 21,000 rows/s for emotion's short tweets, including download.
- The streaming pass is CPU-bound in Python (canonical encoding + xxh3 per row). At these rates a 5 GB full scan of short-text data would take tens of minutes, not the ~7 minutes of download estimated in PLAN §5.5.
- 14–19 HTTP requests per dataset.

### Problems found and fixed during the build

1. The DuckDB examples and leakage queries built per-group lists, which cannot spill. They hit Out-Of-Memory under a memory cap. Both now use only aggregates, joins and windows; tested at 64 MB with 1.1 M rows (32 MB is below DuckDB's floor for these joins).
2. The no-conversion fallback treated `nvidia/simready-assets`' `.metadata/*.json` package files as data. Now hidden paths are never data, and a viewer-disabled repo without `configs` is `not checked`.
3. `cais/hle`'s `## ✏️ Citation` heading and its `[Website] | [Paper] | [GitHub]` links were missed. Both rules are clarified in PLAN §5.1 and covered by tests.
4. IMDB's unlabelled split (`-1`) showed up as "different labels" and "absent from train". `-1` is now treated as "no label" for ClassLabel columns.
5. Sampled label shares are biased on files sorted by label (row groups are clusters). The report now says so under sampling.

### Not done / open

- CI (2.13) not run; nothing pushed. Python 3.11 and 3.13 not tested locally (only 3.12 is installed).
- HF-id/SPDX validity, licence consistency and provenance: Phase 3. Reports list them under "Not checked".
- `config.py` reads flags and `DATASETVET_*` environment variables; a config file is not supported yet.
- The footer phrase "you may" conflicts with the Phase 5 banned-words list (PLAN §12).
- Peak memory was not measured (no `time`/`psutil` on this machine).
- Throughput suggests the 5 GB full-scan default may be slow for short-row datasets; worth re-measuring in task 4.1 before fixing the launch-scan limits.

---

## Phase 3: licence consistency and provenance (2026-11-19, Opus 5.5, high effort)

Run in one Claude Code session (desktop app) on the owner's Windows 11 laptop, Python 3.12.10. Every live call was anonymous: no HF token and no `GITHUB_TOKEN`, so the GitHub token path is tested offline only. Only free endpoints were used.

### Owner decisions on the Phase 2 open questions (given at the start of Phase 3)

| question | decision | where |
|---|---|---|
| Built-in matcher in the plain install? | **Yes**: deterministic, against official SPDX licence texts (askalono-style), no AI, small and dependency-light. Phase 4 evaluates built-in and ScanCode **separately** on the same answer key | `licences/matcher.py`; PLAN §4, §8 (configurations renamed `builtin` / `scancode`) |
| Sampling | **Many small chunks spread across each file**, not whole row groups; keep the label-balance warning | `checks/health/scan.py`; PLAN §5.5 |
| Footer vs banned words | **Reword**: "Facts only, not legal advice. …" | `model.FOOTER`; `tests/test_wording.py` |

### Built

| task | files | state |
|---|---|---|
| 3.1 HF licence ids | `data/hf_licence_ids.csv`, `licences/hf_ids.py` | all 83 ids on HF's list (hub-docs `fd6cf1f`): 53 SPDX, 8 family, 20 non-SPDX, 2 special. The card check now gives `invalid` for a value that is neither an HF nor an SPDX id. The network test passes against today's list |
| 3.2 SPDX wrapper | `licences/spdx.py` | `license-expression` 30.4.4 (+ `boolean.py`), 1.5 MB. `GPL-2.0` = `GPL-2.0-only` ≠ `GPL-2.0-or-later`; subset relation as specified |
| 3.3 properties | `licences/properties.py`, `data/cc_elements.csv` | OSI / FSF / deprecated from the SPDX list; CC elements and deed URL for the 53 CC licences on the SPDX list (5 deed URLs spot-checked live: all HTTP 200). Nothing else is emitted (test) |
| 3.4 ScanCode wrapper | `licences/scanner.py`, `pyproject.toml` `[scan]` | `--scanner builtin\|scancode\|auto`. Missing ScanCode is a clear error for `scancode` and a fallback for `auto`. **Run for real** (below) |
| 3.5 resolvers | `hubs/github.py`, `hubs/web.py`, `http.py` (per-host headers) | GitHub anonymous: zero `api.github.com` calls (test). Token path labelled "GitHub's detection (licensee)"; the token goes to api.github.com only (test) |
| 3.6 licence consistency | `checks/licence.py` | one result per comparison, four statuses, the PLAN §5.2 sentence format (a test checks it word for word) |
| 3.7 provenance | `checks/provenance.py`, `hubs/huggingface.py` `parent_refs` | mismatch, cycle, depth and URL-parent tests |
| 3.8 install docs + CI | `docs/INSTALL.md`, `ci.yml` job `scan-windows` | **written, not run in CI** (nothing pushed); the same steps were run locally |
| 3.9 built-in matcher | `licences/matcher.py`, `data/spdx_licences.json.gz` (249 KB), `tools/vendor_spdx.py` | below |
| 3.10 chunked sampling | `checks/health/scan.py` | below |
| 3.11 footer + wording test | `model.py`, `tests/test_wording.py` | the footer, licence properties and rendered reports pass the banned-phrase regex |

**Checks:** `pytest` 295 passed and 3 skipped (the ScanCode-only tests, which pass in the scan venv), plus 2 `network` tests passing; `ruff check src tests tools` clean; `mypy src` clean.

### Built-in matcher: how it works and what was measured

- **Data:** SPDX licence list **v3.29.0** (released 2026-09-16), 92 texts: every SPDX licence HF's id list maps to, other versions of those families, and common data licences (ODbL, ODC-By, OGL-UK-3.0, DL-DE-BY-2.0, CC ports such as CC-BY-3.0-IGO). Identical normalised texts form 5 pairs (GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, AGPL-3.0: each `-only` text = its `-or-later` text), so 87 distinct texts.
- **Full text:** Dice over word bigrams ≥ 0.90 means "is this licence"; containment ≥ 0.95 means "contains this licence".
- **Problem found and fixed:** with bigram *sets* (first version), CC-BY-1.0 vs CC-BY-SA-1.0 scored 0.997 and CC-BY-4.0 vs CC-BY-SA-4.0 scored 0.964, so near-identical licences could tie. With bigram *multisets*, every one of the 92 texts identifies itself at ≥ 99, and close relatives are told apart (MIT / MIT-0 / X11, ISC / 0BSD, BSD-2 / BSD-3, CC-BY / CC-BY-SA at 1.0 and 4.0, GPL-3.0 / AGPL-3.0). Tested.
- **Notices and URLs:** exact names, ids and short forms in a licence context; licence URLs from the SPDX list's `seeAlso` and from creativecommons.org. Tests found two bugs, both fixed: a CC URL's `/legalcode` was read as a country port (`leg`), and the names inside a full LGPL text (it names the GNU GPL) were counted as separate statements.
- **Speed (this laptop):** data load 0.12 s, text index 0.14 s, a full GPL-3.0 text 0.06 s. The wheel is 336 KB including the data.

### Chunked sampling: measured

- Each file read is cut into slots of `min(100, quota // 100)` rows. Slots are drawn with the seed until the file's share of the quota is met.
- IMDB, `--max-scan-bytes 30MB --sample-rows 5000 --seed 0`: train labels **51.8 / 48.2** (neg / pos), test 52.8 / 47.2. Phase 2's row-group sampling gave **70 / 30** on the same file; the true split is 50 / 50. 14 s.
- Files can still be ordered (e.g. one label per file) and not every file is read, so the label table keeps its warning and now names the chunk size (12–25 rows in this run).

### Live runs (anonymous, 2026-11-19, `--no-data`)

The set: 5 datasets with licence mismatches recorded in the DPI data (`Data-Provenance-Collection` `data_summaries` at commit `ce6662d`, 109 files), 2 with declared parents, and IMDB as a control. "DPI record" is what the DPI recorded (card YAML at audit time vs GitHub's licence or the expert licence).

| dataset | DPI record | built-in result | ScanCode result |
|---|---|---|---|
| `tatsu-lab/alpaca` | card CC BY-NC 4.0, GitHub licence Apache 2.0 | README `consistent` (CC-BY-NC-4.0, line 130); repo `LICENSE` **`inconsistent`** (Apache-2.0, score 98); repo `DATA_LICENSE` `consistent` (CC-BY-NC-4.0, score 99) | same for both files; README `unknown` (it found `LicenseRef-scancode-proprietary-license` at line 111, and nothing ≥ 90 for the CC sentence) |
| `abisee/cnn_dailymail` | card Apache 2.0; GitHub and expert MIT | README `consistent` (Apache-2.0, line 267); `github.com/abisee/cnn-dailymail` `LICENSE.md` **`inconsistent`** (MIT, score 100) | same for the repo; README `unknown` (nothing ≥ 90) |
| `hotpotqa/hotpot_qa` | card CC BY-SA 4.0, GitHub Apache 2.0 | README `consistent`; `github.com/hotpotqa/hotpot` `LICENSE.txt` **`inconsistent`** (Apache-2.0) | same for the repo; README `unknown` |
| `GEM/wiki_lingua` | card CC BY-NC-SA 3.0, GitHub CC0 1.0 | README `consistent`; `github.com/esdurmus/Wikilingua` `LICENSE` **`inconsistent`** (CC0-1.0, score 100) | same for the repo; README `unknown` (proprietary-license rule) |
| `OpenAssistant/oasst1` | card Apache 2.0, expert CC BY 4.0 | README `missing` (no licence statement in the body); repo `LICENSE` `consistent`; `github.com/LAION-AI/Open-Assistant` `LICENSE` `consistent` | identical |
| `stanfordnlp/squad_adversarial` | not in DPI; declares `extended\|squad` | README and source `consistent` (MIT). Provenance: parent `rajpurkar/squad` **`inconsistent`** (MIT vs CC-BY-SA-4.0); grandparent `legacy-datasets/wikipedia` `unknown` (its card lists `gfdl`, a family id) | identical |
| `dlb/plue` | not in DPI; declares `extended\|glue` | README `missing`; `github.com/ju-resplande/PLUE` `LICENSE.md` `inconsistent` (card LGPL-3.0, file is the GPL-3.0 text, score 100); parent `nyu-mll/glue` `unknown` (`license: other` without a name) | identical |
| `stanfordnlp/imdb` | control | README `missing` (licence section holds only `[More Information Needed]`); no source licence, no parents | identical |

- The DPI's recorded card-vs-GitHub mismatches were reproduced for all 4 datasets that have one (alpaca, cnn_dailymail, hotpot_qa, wiki_lingua), each GitHub file pinned to a commit. For oasst1, the DPI expert licence (CC BY 4.0) is a judgement datasetvet does not make: the card, the repo's LICENSE and the source repo all say Apache-2.0.
- The two scanners agreed on all 9 licence-file and source comparisons and all 3 provenance comparisons. They differed on README prose in 4 of 8 datasets: the built-in matcher found the licence statement, while ScanCode at score ≥ 90 abstained or matched a `LicenseRef-scancode-proprietary-license` rule. Phase 4 measures this on the full key.
- 10–22 HTTP requests per dataset with links on; 8–23 s per dataset (GitHub is paced at one request per second).
- Links: all `ok` except `open-assistant.io` (`unreachable`).

### ScanCode extra, installed and run (task 3.4)

- Venv at a short path (`~\.dvscan`), `pip install -e ".[scan]"`: **157 s**, **774 MB**, scancode-toolkit-mini 32.5.0, pluggy 1.5.0, run from PowerShell.
- **New conflict found:** pytest 9.2 requires `pluggy>=1.6`. Installing it upgraded pluggy to 1.7.0, which broke ScanCode again (`did not find any 'plugincode.location_provider' hooks`). With `pytest<9` (8.4.2) and `pluggy<1.6`, both work. The CI scan job pins `pytest<9`.
- **ScanCode score finding:** "released under the CC BY-NC 4.0 license" scores **50**; "Licensed under CC BY-NC 4.0." scores 99; "License: cc-by-nc-4.0" scores 100. At the planned threshold of 90 the first is dropped. The threshold is tuned on the Phase 4 dev split only.
- The scan venv was deleted after the runs; `docs/INSTALL.md` re-creates it in about 3 minutes.

### Other problems found and fixed

1. HF's old card template gives `github.com/huggingface/datasets/blob/master/CONTRIBUTING.md` as the "Repository" of many legacy datasets (IMDB). Read as a source, it compared the card with the `datasets` library's Apache-2.0 licence. That link is now skipped for licence comparisons.
2. The same template's "Licensing Information: [More Information Needed]" made the README `unknown` ("mentions a licence"). It is now `missing`, with a note naming the placeholder; table-of-contents lines are ignored.
3. The terminal "Not checked" line had grown into one long sentence; it is now a list.

### Corrections to the plan

- The plain install is no longer licence-blind (PLAN §4 rewritten; the old text is struck through).
- `SourceResolver.licence_claims` became `read()` (PLAN §6).
- A GitHub source with no licence file is `unknown` anonymously, and `missing` only when GitHub's API confirms (PLAN §5.2).
- Provenance compares each grandparent with its own child, not with the root dataset (PLAN §5.3).

### Not done / open

- CI (both jobs) not run; nothing pushed. Python 3.11 and 3.13 not tested locally.
- The token paths (HF and GitHub) were tested offline only; no token was present.
- **The SPDX licence list does not state a licence for its own data** (GitHub `NOASSERTION`; the README and spdx.org say nothing; the site footer says "All Rights Reserved"). The package vendors 92 licence texts and list metadata. Owner to decide before release (PLAN §12).
- A repository's LICENSE often covers code, not data (hotpot_qa; alpaca's `LICENSE` vs `DATA_LICENSE`). The report states both licences and that they differ; it does not say which covers the data. Worth counting in the Phase 4 disagreement audit.
- Built-in matcher: no non-SPDX licences and no paraphrases ("research use only"). Its abstention rate against ScanCode's is a Phase 4 measurement.
- Thresholds (built-in Dice 0.90 / containment 0.95; ScanCode 90) are untuned. Phase 4 tunes them on the dev split only.

## Phase 4: accuracy evaluation and launch scan (2026-11-19 to 2026-11-21, Opus 5.5, high effort)

Run in one Claude Code session (desktop app) on the owner's Windows 11 laptop, Python 3.12.10, Claude Pro plan. The owner said they were logged in with `huggingface-cli login`, but `huggingface_hub` found no token (no `HF_TOKEN`, no file at `~/.cache/huggingface/token`), so **every Hugging Face call was anonymous**. No `GITHUB_TOKEN`. Results, method and limits are in `RESULTS.md`. Commits: `1d8f4e4` (part 1), `bc89e12` (part 2), `cdb210e` (faster fetching), and the final commit with the results. Nothing pushed.

### Owner decisions (given at the start of Phase 4)

| question | decision | where |
|---|---|---|
| SPDX licence texts (their licence is not stated) | **Ship no licence text.** Only list metadata and a derived fingerprint index, with a script that regenerates both from the official SPDX release | `tools/vendor_spdx.py`, `data/spdx_fingerprints.json.gz`; PLAN §4, §12 |
| A question to SPDX | Draft a short GitHub issue; the owner posts it | `docs/drafts/spdx-license-list-data-issue.md` |
| Launch scan | Top ~500 by downloads, resumable, rate-limit friendly, huge datasets sampled and labelled, run in batches with a usage check between them | `launch/` |
| Faster fetching (asked mid-scan) | Combine a git pack and parallel downloads, **with an equivalence test first**; then commit it so the scan's config hash names a commit | `cdb210e` |

### Built

| task | files | state |
|---|---|---|
| SPDX: no texts shipped | `tools/vendor_spdx.py`, `data/spdx_licences.json.gz` (249 KB → 8.5 KB), `data/spdx_fingerprints.json.gz` (281 KB), `licences/matcher.py` | per group of identical texts: the multiset of 64-bit BLAKE2b hashes of its normalised word bigrams, delta-encoded against one shared table; no word stored. `--check` rebuilds both files byte for byte. Matcher scores unchanged (all matcher tests pass against the index); tests needing a real text read a git-ignored cache and skip without it |
| 4.1 list + budget | `launch/freeze_list.py`, `launch/lists/top500-2026-11-19.json` | 500 datasets, each pinned to a sha; sizes known for 251 (291 TB of Parquet); 829 requests, 23 min |
| 4.2 runner | `launch/run.py`, `launch/state.py` | SQLite state per (dataset, tier) with config hash; `--max`, `--batch`, `--retry-failed`, `--shard I/N`; Ctrl-C finishes the dataset in flight. Part 2: the config hash includes the git tree ids of `src/`, `launch/run.py`, `launch/state.py`, `pyproject.toml`, and the scan refuses a dirty tree |
| 4.3 key | `eval/build_key.py`, `eval/dpi_licence_map.csv` (52 names), `eval/key/` | DPI `ce6662d`: 109 files, 3,718 entries, 3,492 with an HF repo, **792** unique repos (PLAN §8 gave 804 from the Phase 1 probe); 81 dropped (entries disagree), 3 dropped (no card licence recorded); 708 key rows; 371 for Q3 (239 consistent, 80 inconsistent, 52 missing) |
| 4.4 revisions | `eval/revisions.py`, `tests/test_eval_revisions.py` | latest `main` commit at or before the DPI file's last change |
| 4.5 dev + freeze | `eval/run.py`, `eval/config.yml`, tag `eval-config-v1` (`1d8f4e4`, local) | built-in: all 8 grid points gave 79/116, kept 0.90 / 0.95. ScanCode: ≥ 50 gave 76 (≥ 90: 66), so 50. `eval/run.py` refuses the test split unless config, runner and `src/` match the tag |
| 4.6 test + metrics | `eval/metrics.py`, `eval/results/` | below; the post-hoc "own repo only" view is labelled exploratory in the code and in RESULTS |
| 4.7 launch scan | `launch/results/`, `launch/summarize.py`, `launch/check_listing_cap.py` | below |
| Faster fetching | `hubs/gitpack.py`, `checks/health/fetching.py`, `http.py`, `--no-git-fetch`, `--fetch-workers` | below |

**Checks** (final commit): `pytest` 320 passed and 3 skipped (ScanCode-only); `ruff check src tests tools eval launch` clean; `mypy src` clean, and `launch/summarize.py`, `launch/check_listing_cap.py` clean.

### Accuracy evaluation (test split, 245 rows scored)

| | built-in | ScanCode (≥ 50) |
|---|---|---|
| agreement, decided rows | 76.0% (139/183; 69.3–81.6%) | 74.9% (131/175; 67.9–80.7%) |
| abstention | 25.3% | 28.6% |
| kappa | 0.53 | 0.52 |
| `inconsistent` precision / recall | 37% / 28% | 34% / 26% |

- The built-in matcher is at least as close to the DPI key as ScanCode, with fewer abstentions; the intervals overlap. Skipping the 774 MB extra costs nothing measurable on this key.
- Main disagreement: a source repo's LICENSE covers its code, the DPI's expert set records the data licence (27 "expected consistent → ours inconsistent" for built-in; 33 of our `inconsistent` come from a GitHub source).
- Q1 card parsing 91.8% (225/245); Q2 GitHub source licences 45/45.
- 8 test rows excluded: the repo's history now needs a login (HTTP 401).
- The 30-row disagreement samples per scanner are written; **not labelled yet** (owner).

### Launch scan

- **Tier A** (2026-11-19, `1d8f4e4`, config hash `d0b085a50bef68aa`, before code trees were hashed): 499 of 500; 2,921 requests, 2,937 s. Card licence present in 299; of those 37 have an `inconsistent` comparison.
- **Tier B, first attempt** (2026-11-19, config hash `d1d12f8a1d35321e`): 200 MB full-scan limit measured about 4 MB/s (over 4 hours for the list), so the limits were halved after 7 datasets: **100 MB full scan, 10,000-row sample, 100 MB download cap, seed 0**. Three shards in parallel. A timezone-aware timestamp failed without `tzdata` on Windows (fixed in `pyproject.toml`, test in `test_rowhash.py`). The run was stopped after the owner asked about speed: one repo of 5,410 small files had taken 55 minutes, one HTTP request per file, no 429s.
- **Tier B, final** (2026-11-20 14:34 to 2026-11-21 06:35, `cdb210e`, config hash `2472d09329f26eb6`): 3 rounds of up to 60 per shard, usage checked before each round (5-hour window at 18% or less), then one retry. 494 done, 6 failed; 392 with data read (195 full, 197 sampled), 102 `not checked`; 602,535 requests, 75,801 s across 3 processes; no 429.
- Findings, counts and intervals: RESULTS §2.

### Faster fetching: what was measured

- **Cause of the slowness:** serial per-file latency (0.3–1 s), not rate limits; plus `http.py` spaced requests to the Hub's download CDN (`*.hf.co`) 1 s apart like any non-API host. The normal CLI had the same spacing.
- **Ideas tried and dropped:**
  - Asking the Hub's git server for many explicit blob ids fails above about 10 ("fatal: expected 'packfile'").
  - `git ls-tree -l` in a partial clone fetches every blob lazily; `GIT_NO_LAZY_FETCH=1` and `cat-file --batch-all-objects` avoid it.
  - The tree API pages 1,000 entries at a time; `siblings` with `blobs=true` gives blob ids and sizes in one call.
  - Skipping duplicate files by blob id was dropped: it would make reports depend on the fetch route.
- **Equivalence** (`launch/fetch_equivalence.py`, 40 datasets: the 12 slowest and 28 random): 39 reports identical field by field to the one-file-at-a-time route at the same revision; the 40th differs only in its Parquet-conversion commit, which HF rebuilt on 2026-11-20 (the old route shows the same change). Time 11,453 s → 1,952 s; 12 slowest 10,639 → 1,579 s; `gradio/frontend` 3,302 s → 72 s (10,822 → 2 requests, 5,410 files from a 1.77 MB pack).
- **In the final Tier B:** the git pack served 49,975 files for 22 datasets; 301,441 files came over HTTP, up to 8 at a time.

### Problems found and fixed

1. Fetch-ahead could pass the download cap by one file (the file being read was not counted as in flight). Caught by a unit test, fixed before the equivalence run.
2. `launch/state.py`: parallel shards needed a SQLite busy timeout.
3. `tzdata` on Windows (above).
4. The launch scan could run on uncommitted code, so its config hash did not name a commit. Fixed in part 2 (code trees in the hash, dirty tree refused).
5. `launch/summarize.py` now records the config hash(es) behind each tier's rows, timing, scan source and fetch-route counts, and marks cut-off listings.

### Problems found and not fixed (they need a code change, which would re-run the scan)

1. **The Hub's `siblings` list stops at 100,000 entries**, and the HF adapter takes the file list from it. 69 of the 169 datasets checked have exactly 100,000. 64 Tier B scans read a partial list (18 labelled "Full scan"); 8 Tier A datasets got 157 false "missing file" link results. The four slowest datasets (1.9–4.2 h each, 59% of Tier B time) are among them. Fix: page through the tree API when `siblings` has 100,000 entries. RESULTS gives every share with and without them.
2. **"corrupt" overstates what happens:** 47 datasets had a file that could not be read; 38 are `.json` files that are not row tables (tokenizers, configs), 8 hit a datasetvet bug (`AttributeError` on a JSON array of non-objects), 1 a 404 for a listed file. 0 of 230 Parquet-conversion scans. The check needs another name and should skip non-data JSON.
3. `ValueError` on nanosecond timestamps that do not fit a Python `datetime` (1 dataset); `ArrowIndexError` (2 datasets, not diagnosed).
4. `SCANCODE_MIN_SCORE` in `licences/scanner.py` is still 90; the frozen eval config uses 50. Changing the default is a release decision (the eval tag pins `src/`).

### Not done / open

- The owner's labels for the 60 disagreement rows (`eval/results/disagreements-*.csv`).
- Post the SPDX issue (`docs/drafts/spdx-license-list-data-issue.md`). The list metadata still comes from the unlicensed source.
- **The old licence texts were in git history** (Phase 3 commit `3a6b650`, now `8a92854`; `data/spdx_licences.json.gz` at 249 KB). Removed from all history in Phase 4.5; see the commit ids there.
- No HF token was found: `hf auth login` (from the venv) would double the API allowance and read gated cards.
- CI (both jobs) not run; nothing pushed. The tag `eval-config-v1` is local.

## Phase 4.5: fixes from the launch scan, and the rescan (2026-11-21 to 2026-11-22, Sonnet 5.5, high effort)

Fixes, tests and rescan ran on Sonnet 5.5 (commit `4085159`). The closing steps (summary, RESULTS, this entry, the commit) ran on Opus 5.5 in the same Claude Code session after a context reset. The frozen accuracy eval (`eval-config-v1`) was not re-run or changed. Every Hugging Face call was anonymous. A token was found on the laptop during this phase and was hidden on purpose (`HF_TOKEN_PATH` set to a file that does not exist), so the rescan matches the first scan's conditions. The owner chose to keep it that way when asked whether a free login should double the API allowance. Nothing pushed.

### Owner's brief

Fix what the launch scan found:
- the 100,000-entry file list;
- three reader bugs, each with a failing test first;
- the "corrupt" check counting non-data files.

Then rescan only the affected rows under the new config hash, update RESULTS from the fixed scan with a "what the first scan got wrong" section, and commit. Finally, remove the full-text SPDX file from git history before any push.

### Built (`4085159`)

| fix | where | behaviour |
|---|---|---|
| File list past 100,000 | `hubs/huggingface.py` (`listing`), `hubs/base.py` | when `siblings` has 100,000 entries, the tree API is paged (1,000 a page, `Link: rel="next"`, host must stay huggingface.co, a repeated page or more than 5,000 pages stops). A list that cannot be read whole is `complete=False`: the scan says **"Partial scan"**, no missing-file result is made, the licence-file search says it may have missed a file, the git route is off. Never cached as complete |
| Nanosecond timestamps | `checks/health/values.py`, `rowhash.py` | `timestamp[ns]` values that are not whole microseconds are hashed as integer nanoseconds (also inside structs and lists); values 1 ns apart still differ |
| `ArrowIndexError` | `checks/health/scan.py` | pyarrow's JSON reader builds an invalid array for some nested null lists; its result is checked with `validate(full=True)` and Python's parser reads the file instead when it fails |
| JSON arrays of non-objects | `checks/health/scan.py` | one row per item in a column `value`; an array mixing objects and non-objects is a file that could not be read as rows |
| One bad batch | `checks/health/runner.py` | stops that file, not the dataset |
| "corrupt" → `health.unreadable` | `model.py`, `checks/health/empty.py`, `runner.py` | "Files that could not be read as rows", each file with a kind: `invalid`, `reader_limit`, `empty`, `download`; the wording never says "corrupt" (test) |
| Non-data files | `hubs/huggingface.py` | tokenizer/model/package config JSON and `site-packages`, `dist-packages`, `node_modules`, `__pycache__` are skipped unless the card's `configs` names them; a repo with nothing left is `not checked` |
| Launch tools | `launch/run.py --only`, `rescan_set.py`, `check_non_data.py`, `check_listing_cap.py --all`, `summarize.py` | the rescan set with a reason per dataset; rescanned rows marked; the first scan's summary kept in `launch/results/first-scan/` |

**Tests written first:**
- 38 new tests, in `tests/test_listing.py` (14), `tests/test_read_bugs.py` (13) and `tests/test_unreadable.py` (11).
- The listing tests simulate a repo of more than 100,000 files: 99,999 `siblings` entries plus tree pages beyond them. They check that a card path past the old cut-off is no longer "missing" and that a full listing past the cap gives "Full scan".
- Each bug test failed before its fix.

### The rescan

- **Rescan set** (`launch/rescan_set.py` → `launch/results/rescan-set.json`):
  - Tier B, 99 datasets: 64 with a cut-off list, 47 with the old "corrupt" result, 12 that read files now skipped as non-data (found by `check_non_data.py`; the "corrupt" criterion alone would have missed them), and the 3 bug datasets. A dataset can have several reasons.
  - Tier A, 8 datasets: the ones with false missing-file results.
- **Listing check over all 500** (`check_listing_cap.py --all`, API only): 136 have a cut-off `siblings` list.
- **128 Tier A not rescanned.** They had a cut-off list but no missing-file result. I started them as an extra process; the owner stopped it to keep to the brief and to speed up the rest. The one row it had finished (`neashton/windsorml`) was put back to its first-scan result. They are listed in `rescan-set.json` and as a limit in RESULTS.
- **Runs** (`run.py --only`, plan usage 18% before starting):
  - Tier B in 3 shards, one batch each: 2026-11-21 12:58 to 22:50 (+04:00), 81,537 s of checking, 317,975 requests, 99 of 99 done.
  - Tier A, one process: 7,259 s, 3,760 requests, 8 of 8 done.
  - Config hashes: `fe7d94fb698d5f41` (B) and `7c024a7a384b9026` (A).
- **Speed.**
  - The slow part was the anonymous API allowance (500 calls per 5 minutes), shared by 4 processes, while each 100,000+ file repo was paged at 1,000 entries per call. A check during the run showed 20 of 500 left.
  - Repos with more than 100,000 files took 20–50 minutes each under that contention. One user checking one dataset has the allowance alone; that was timed afterwards (next bullet).
- **Timing one very large repo alone** (`launch/time_large.py`, owner's decision, logged in for this run only; RESULTS section 2): `PGCodeLLM/radin-cyber-backups`, 389,052 files (146,744 data files; the other probed repos had 376k, 773k and 1M files).
  - Listing, cold cache: 223.8 s for 615 pages (0.36 s a page, about 36 s per 100,000 files).
  - Launch-style sample read (listing cached): 321 s, 9,999 rows, 75.9 MB.
  - Default read: stopped at the 20-minute cap as agreed, not finished. `default/test` took 218.6 s for 6,307 files (34.7 ms a file); `default/train` (136,099 files) was still running. Projected about 85 minutes for this repo and about 1 hour for 100,000 data files, from one split's rate, so an estimate.
  - Used: the README now says "expect about an hour for a full read of a repo with 100,000 data files"; PLAN Phase 5 task 5.9 adds the large-repo warning before scanning (file count, estimated time, sampled scan suggested).
  - `nvidia/PhysicalAI-WorldModel-Synthetic-Autonomous-Driving-Scenarios` went from 4.2 h (cut-off list, HTTP) to 34 min (121,076 files from one git pack).

### Results (RESULTS.md §2)

- Tier B: 497 done, 3 failed (all no longer on the Hub); 394 with data health run, 356 with at least one row read.
  - Over those 356: duplicates in 73 (20.5%; 16.6–25.0%), leakage in 24 (6.7%; 4.6–9.8%), files that could not be read as rows in 32 (9.0%).
- Tier A: 157 false missing-file results → 0. Datasets with a dead link: 23 of 168 → 16 of 166.
- **Found while checking the rescan:**
  - `lyzenghq/banned-historical-archives`: 59,957 listed files return HTTP 404 from the Hub's storage (the `resolve` URL redirects to `cdn.hf.co`, which 404s; checked for 3). This is the repo, not datasetvet.
  - 38 "scanned" datasets read no row: 37 samples stopped at the launch download cap of 100 MB, and 1 had only unreadable files. The first scan had the same problem (39), and its RESULTS counted them as "data read". Shares are now over datasets with at least one row read, in both the new numbers and the first-scan comparison.
  - `McGill-NLP/WebLINX-full` keeps one missing-file result. It is real: the card names `chat/test_iid.csv`, which the tree API does not list.

### Problems found and fixed in this phase

1. The extra Tier A process went beyond the brief. It was stopped and its one row reverted (above).
2. A heredoc expanded escape sequences in a source line during part 1; fixed before the commit.

### Not done / open

- **History rewrite.** Decided by the owner and done as the last step (old to new commit ids in the table below). Reason: SPDX's `license-list-data` repo, where Phase 3's 92 licence texts came from, declares no licence (GitHub shows `license: null`; an issue about it is drafted). Without a licence it is unclear whether that copy may be redistributed, so only a derived fingerprint index (no readable text, rebuilt from the official source) is shipped. The full texts in history (`src/datasetvet/data/spdx_licences.json.gz`, 249 KB, blob `deda55b`, commit `3a6b650`) would undo that decision on the first push, since anyone can check out old commits. Nothing was public yet, so changing commit ids cost nothing.
- The 128 Tier A datasets with a cut-off list but no missing-file result.

### History rewrite (Phase 4.5, step 6)

Run last, before any push, in place with `git filter-repo --strip-blobs-with-ids` (git-filter-repo 2.47.0 from a throwaway venv, `--force` because the repo is not a fresh clone). The one stripped blob is `deda55bacfd535f1475c2bc8a1e0fc708f3e3024`, the 249,387-byte full-text `src/datasetvet/data/spdx_licences.json.gz` added by `3a6b650`. The 8,467-byte metadata file of the same name from `5254aab` on is a different blob and stays. A backup bundle of the whole old history is outside the repo (`~/datasetvet-backups/datasetvet-before-filter-repo-2026-11-22.bundle`, with `old-commit-ids.txt`); keep it until the first push, then it can be deleted, since it still holds the texts.

| commit | old | new |
|---|---|---|
| Rename project to datasetvet | `f1e9d06` | `f1e9d06` (unchanged) |
| Phase 3: licence consistency and provenance | `3a6b650` | `8a92854` |
| Phase 4 (part 1) = tag `eval-config-v1` | `5254aab` | `1d8f4e4` |
| Phase 4 (part 2) | `5c9076c` | `bc89e12` |
| Faster data fetching | `a3f5428` | `cdb210e` |
| Phase 4 (part 3) | `9151cd8` | `ae18a67` |
| Phase 4.5 (part 1) | `0ba2ea4` | `4085159` |
| Phase 4.5 (part 2) | `35d5602` | `3556a4f` |
| Phase 4.5 (part 3) | `acccaa2` | `205d4dd` |

The first two commits of the repo (`cde4e6c`, `c522ec8`) come before the file and are unchanged. Doc mentions of the old ids (this file, RESULTS.md, one launch docstring) were changed to the new ids in the commit after the rewrite. The launch state and reports (`launch/state.sqlite`, ignored by git) still name the old `0ba2ea4` as the code of the rescan; its config hash names the code by git tree ids, which did not change.

Checks after the rewrite:
- The stripped blob is gone: `git cat-file -t deda55b` fails, `git rev-list --objects --all` lists no object with that id, `git fsck --full` is clean, and the repo's pack is 780 KiB.
- No commit has a `spdx_licences.json.gz` larger than 8,467 bytes (`3a6b650`'s rewrite has none; every commit from `5254aab` on has the 8,467-byte file).
- `eval-config-v1` (a lightweight tag) now points to `1d8f4e4`. The tree is `a36f321`, the same as before, and so is every later commit's tree (checked for all 7 commits from `5254aab` on). So the code is identical and only the commit id changed. `src/` was not touched, so the config hashes of the launch scan (which use tree ids) are still valid.
- `pytest`: 360 passed, 3 skipped (ScanCode-only), 2 deselected.
- Other full-text hits in history: the project's own `LICENSE` and a few short licence phrases in `tests/test_matcher.py`. Neither is the SPDX text collection.
- `SCANCODE_MIN_SCORE` default 90 vs the eval's 50; the disagreement labels; posting the SPDX issue (all from Phase 4).
- CI not run; nothing pushed.

**Checks** (commit of this entry): `pytest` 360 passed, 3 skipped (ScanCode-only); `ruff check src tests tools eval launch` clean; `mypy src` clean, and the four launch scripts clean.

## Phase 5: polish and launch prep (2026-11-22, Sonnet 5.5, medium effort)

Run in one Claude Code session (desktop app), Windows 11, Python 3.12.10. Every Hugging Face call was anonymous (`HF_TOKEN_PATH` pointed at a file that does not exist, as in Phase 4.5); no `GITHUB_TOKEN`. No token of the owner's was read, typed or stored. Nothing was pushed, no repo was created, nothing was uploaded to PyPI. Not committed until the last step (below).

### Inputs the brief named that were not available

| item | what was found | state |
|---|---|---|
| 1. Fixes for the Opus review | The brief had the placeholder "[paste them here]" unfilled. No findings file or notes exist in the repo, `BUILD_LOG.md`, `PLAN.md` or the home folder (searched by name) | **not done**: no findings to fix |
| 4. Human audit table | `eval/results/disagreements-builtin.csv` and `disagreements-scancode.csv` (last written 2026-11-19) have an empty label column in all 60 rows, in the repo and on disk | **table not made up.** `eval/audit.py` turns the labels into the RESULTS table once they are filled in (15 tests); RESULTS has a placeholder that says so |

### Decisions and measurements

| task | what was done | measured / result |
|---|---|---|
| 3. ScanCode threshold | `SCANCODE_MIN_SCORE` 90 → **50**, documented in `scanner.py`, PLAN §4, §5.2 and RESULTS | The frozen test run scored 50 only, so `eval/threshold_check.py` scored 50 and 90 together on the 245 test rows (one process, identical inputs; a second look at the test split, labelled so in RESULTS). 50: 131 agree (53.5%; 47.2–59.6%), abstention 28.6%. 90: 110 agree (44.9%; 38.8–51.2%), abstention 39.2%. The 50 run reproduces the frozen result exactly. Row by row: 22 rows agree only at 50, 1 only at 90 (sign test p ≈ 6e-6). Agreement on decided rows is the same (74.9% / 73.8%): the gain is fewer abstentions, and 21 of the 26 rows newly decided are right. So 50 beats 90 and is the default |
| 2 / 5.9. Large-repo warning | `checks/health/large.py`; `pipeline.run_check(confirm=...)`; `--yes`; `ScanInfo.large_repo` | After the file list and the data plan, before any data file is fetched: the file count ("at least" when the list is cut off), data files, an estimate from the measured 34.7 ms a file (a sampled run estimates only the files its quota needs), and the sampled-scan flags (the launch ones, measured 321 s). A terminal is asked "Read the data anyway? [y/N]"; `--yes`, `CI`, `GITHUB_ACTIONS` and non-terminal runs go ahead and still print it; the scan line says "large repo: N files". Declining skips only the data-health scan. 16 tests (the 100,000+ file list is simulated) |
| 5. Action | `action.yml` (composite), `examples/workflow.yml`, `.github/workflows/action-test.yml`; `datasetvet check --md PATH --fail-on STATUS` (exit 3), `report/markdown.py` | The Action's check step was extracted from `action.yml` and run in bash with the same environment variables against `hf:cornell-movie-review-data/rotten_tomatoes`: exit 0, report, job summary and outputs written. **Not run on a GitHub runner** (nothing is pushed). SARIF was not built: code scanning needs a file location in the repo and a Hub dataset check has none. Markdown text from datasets is escaped (tested) |
| 6. README | `README.md`, `docs/demo/demo.gif`, `docs/demo/demo.cast`, `tools/record_demo.py` | The recording is a real, uncached run of `check hf:tatsu-lab/alpaca` (17 s), captured as an asciicast v2 file and drawn to a GIF with pyte and Pillow. asciinema itself does not run on Windows. The numbers come from RESULTS.md and link to it |
| 7. Package | version 0.1.0, `[project.urls]`, sdist file list, classifiers | `python -m build` then `twine check`: both files PASSED. A wheel installed in a clean venv ran `datasetvet check`. `docs/RELEASE.md` has the repo description, topics, the `gh` and `twine` commands and what to check before the first push; none was run. The repo URL in `pyproject.toml` and the README assumes the owner `moelsaka01` (the local git user) |
| 8. Launch posts | `LAUNCH.md` | r/MachineLearning, r/datasets, X (post and two replies), LinkedIn, HF community post; each leads with "40.1% of the top 500 state no licence" and carries the caveats (`inconsistent` precision 37%, agreement is with a best-effort audit, lower bounds) |

### Problems found and fixed

1. The shell tool collapsed backslashes in heredocs (a regular expression and two test strings came out wrong). Caught by the tests and the first live Markdown report; those files were fixed through the edit tool instead.
2. Two new tests built a simulated 100,000-file repo whose card pointed past the cut-off list, so the scan fell back to reading all 100,000 files and hung. The tests now point at files inside the list.
3. PII facts said "1 values match"; singular now.
4. Markdown escaping first escaped every underscore ("rotten\_tomatoes"); it now leaves an underscore inside a word alone.

### Not done / open

- **The Opus review fixes and the human audit table**, above. Both need the owner's input.
- HTML report and badge (5.1, 5.2), the static site (5.5), the optional AI summary (5.6), and the competitor re-check (5.8) were not in the brief and were not done.
- The Action and `action-test.yml` have not run on GitHub; CI has never run (both Phase 2/3 jobs and the new one).
- The demo GIF shows the report appearing at once (stdout is written at the end); it is not an animation of the scan.
- The owner still has to create the repo, push, and upload to PyPI (`docs/RELEASE.md`), and post the SPDX issue and the launch posts.
- 128 Tier A datasets with a cut-off listing remain unrescanned (Phase 4.5).

**Checks** (before the commit of this entry): `pytest` 397 passed, 4 skipped (the ScanCode-only tests; they pass in the scan venv: 4 passed there for `tests/test_scancode.py`), 2 deselected; `ruff check src tests tools eval launch` clean; `mypy src` clean, and the two launch scripts clean.


## Phase 5.5: v2 licence rules and a pre-registered held-out evaluation (2026-11-22, Opus 5.5, high effort)

Run in one Claude Code session (desktop app), Windows 11, Python 3.12.10. Every Hugging Face call was anonymous (`HF_TOKEN_PATH` pointed at a file that does not exist); no `GITHUB_TOKEN`. Rules only: no AI in any rule, baseline or label step. Nothing pushed.

### Owner's brief

Close the gap to the human audit before v0.1:
1. pre-register the goal and metrics, and commit before any rule work;
2. draw a fresh seeded held-out set of 120 launch-scan datasets not in the DPI key, build a blind labelling sheet, and tag `holdout-v1` before labelling;
3. do rule work on dev and the 60 audited rows only: fewer `unknown`, and a source repo's code licence reported as "the source code licence differs";
4. freeze (`eval-config-v2`) and score A (HF tag alone), B (ScanCode alone) and C (datasetvet) on the held-out labels, plus v2 on the old test split marked "no longer blind";
5. report whatever the numbers are.

### Commits and tags (in order)

| step | commit / tag | what |
|---|---|---|
| 1 | `ed0ad4d` | PLAN.md §8.1: goal (kappa ≥ 0.61 on decided rows, abstention < 15%, beat A and B with exact McNemar p < 0.05), metrics, held-out design, rule-work rows, freeze rule; the old test split retired from tuning |
| 2 | `eb8bfad`, tag `holdout-v1` | `eval/holdout/draw.py`, `sheet.csv` (120 rows, label columns empty), `LABELLING.md`, `draw-a.json` |
| 3–4 | `45122c5`, tag `eval-config-v2` | the rules, their tests, `eval/config-v2.yml`, `eval/run_v2.py`, `eval/holdout/predict.py`, `eval/holdout/score.py`, the rule-work run |
| 5 | the commit of this entry | v2 on the old test split, RESULTS §0, README, PLAN |

### Inputs not as the brief assumed

- **"The 60 audited rows" are not audited.** `eval/results/disagreements-builtin.csv` and `disagreements-scancode.csv` still have an empty owner-label column in all 60 rows. They hold 48 distinct datasets, because 12 appear in both samples. These 48 were used as rule-work rows with the DPI key's labels, as the pre-registration says. The human audit table in RESULTS §1 stays a placeholder.
- **Order of looking.** Before writing the pre-registration I printed v1's statuses and comparisons for the dev rows and the 48 datasets, to see what drives `unknown` and the false `inconsistent`s. No rule was written before the pre-registration was committed. No other old test row was printed during rule work.

### Held-out draw

- Launch list 500; 7 are in the DPI collection (any of its 792 HF repos, not only the 708 key rows); `KakologArchives/KakologArchives` removed (sha gone); pool 492; `random.Random(20261122).sample(sorted_pool, 120)`.
- From the sheet: 76 cards state a YAML licence; 24 repos have no README at the frozen sha; 3 gated, all with readable READMEs; 1 deleted since the freeze (`defeatbeta/yahoo-finance-data`, marked, not scored).
- **Problem found and fixed:** the first version read each card through the adapter's `card()`. For a repo whose `siblings` list is cut at 100,000 entries, that pages the whole file tree to find `README.md`. On `assassinlike/everything132` this ran for more than an hour at 2.7 GB of memory. The sheet now fetches `README.md` directly at the sha, with YAML fields from the Hub API when there is no README. The draw itself (seed, pool, order) did not change, and the 81 rows already done were re-read from the HTTP cache.
- The sheet holds only card fields copied verbatim, pinned links, raw URLs found in the card and the gated flag. Card copies are git-ignored in `eval/holdout/cards/`, with their SHA-256 in the sheet.

### Rules (PLAN.md §5.2 "Phase 5.5")

| rule | where | tests |
|---|---|---|
| A source repo's licence file (GitHub, not `DATA_LICENSE`) or GitHub's detection naming only OSI-approved licences, against a card naming a non-OSI licence → `unknown`, "the source code licence differs" | `compare()`, `sides_from_read()` | 11 in `tests/test_licence_rules_v2.py` |
| Several licences in one text: set aside OSI-approved licences the card does not name; the rest equals the card's set → `consistent` | `compare()` | 5 |
| `licence.summary` ("Licence, overall"): missing / unknown (card unclear) / inconsistent / consistent "confirmed" / unknown "unresolved" / consistent "uncontradicted". A source repo's code licence, an anonymous "no licence file found" (its own new sub) and an unreadable stated source are not evidence either way; an unreadable own README is | `summarise()`; renderers count it apart from the comparisons | 8 |

- The OSI-approved flag now decides something. It is the only licence property that does (docstring in `licences/properties.py`, PLAN §5.2).
- Rule switches are module constants that the eval sets per variant, the way v1 patched the matcher thresholds. They are not user options.
- **Selection on the rule-work rows** (164 scored; rows agreeing, abstaining = miss): v1 84; uncontradicted 109; code licence 92 (data-licence card) / 91 (any card); all three 119 (data-licence card) / 118 (any card); all but the set-aside rule 117. Every rule raises the count, so all three are kept, with the data-licence-card condition. Abstention 29.3% → 7.3%; kappa on decided rows 0.497 → 0.499.
- **Tried and not kept:** "uncontradicted" only for data-licence cards. It loses 16 agreeing rows to fix 9.
- **Not fixable by these rules:** 11 rule-work rows where the card, the README and the files agree but the DPI expert chose another licence.

### v2 on the old test split (no longer blind; RESULTS §0)

245 rows scored, the same as v1. Rows agreeing: v1 139, v2 177 (McNemar p ≈ 7e-8), tag alone 179 (v2 vs tag p = 0.82). Abstention 25.3% → 6.5%. Kappa on decided rows 0.53 → 0.46; the tag alone 0.34. `inconsistent` precision 16/43 → 9/17, recall 16/57 → 9/57. 23 of v2's 53 "uncontradicted" rows are ones the key calls `inconsistent`.

**Expectation before any held-out label:** the pre-registered goal is likely missed on kappa and on beating the tag alone. The goal was not changed.

### Problems found and fixed

1. Reading cards for the sheet paged a 100,000+ file listing (above).
2. `eval/run.py` and `launch/run.py` are both module `run`. The new eval test made `tests/test_launch.py` fail to import. Eval scripts now load each other under unique names (`eval/evalmods.py`).
3. The shell collapsed a backslash in a heredoc edit (as in Phase 5). The edit was caught before it was written, and redone with the edit tool.
4. A sheet saved by Excel starts with a BOM; the sheet guard now ignores it (test).

### Not done / open

- **The held-out labels** (owner), then `predict.py` (ScanCode venv, PowerShell) and `score.py`, then RESULTS §0's held-out tables. If fewer than 60 rows are scorable, draw batch b first (`draw.py --batch b`, tag `holdout-v1b`).
- The owner labels of the 60 disagreement rows (Phase 4), still empty.
- Cosmetic, left frozen: the overall sentence joins the names of agreeing comparisons with ";" ("confirmed by README text; source …"). Changing it would move `src/` off the tag; do it after the held-out score.
- The demo GIF and asciicast in `docs/demo/` still show v1 output (the README text excerpt is v2). The launch-scan results (RESULTS §2) were made by v1 code and were not re-run; with v2 the "inconsistent" share there would fall.
- `LAUNCH.md` quotes v1's `inconsistent` precision (37%); revisit after the held-out score.

**Checks** (before the commit of this entry): `pytest` 433 passed, 4 skipped (ScanCode-only; in the scan venv `tests/test_scancode.py` and the rule tests: 30 passed, 1 skipped), 2 deselected; `ruff check src tests tools eval launch` clean; `mypy src` clean.

## Phase 5.5, part 2: held-out score, v2 launch re-run, docs (2026-11-22 to 2026-11-23, Opus 5.5, high effort)

Same session as part 1 (desktop app, Windows 11, Python 3.12.10). Every Hugging Face call anonymous; no `GITHUB_TOKEN`. Nothing pushed.

### Owner's brief

The owner's labels are in. Commit them and compare them with the AI first pass. Run `predict.py` and `score.py`, and report against the pre-registered goal, misses included, with the `confidence = sure` subset apart. Update RESULTS, README and LAUNCH.md:
- the labels described exactly as "AI-assisted labels, every row reviewed and corrected by the author against the pinned cards", never as an independent human audit;
- the DPI comparison kept as the independent human key;
- the Limits line "the author labelled the held-out set, starting from AI drafts", with the number of labels changed;
- lead with what the HF tag can't do;
- report how the licence status compares with the tag alone, even if it ties or loses;
- no v1 numbers in LAUNCH.md, the README accuracy section or the demo.

Then make the deferred wording fix, run the checks and commit. After the v2 launch numbers: use 36.6% as the headline, put contradiction recall under Limits and on a v0.2 list.

### Commits

| commit | what |
|---|---|
| `89d2985` | the owner's labels: `eval/holdout/sheet.csv` replaced by the owner's file; a diff showed only `expert_licences`, `expected_status`, `confidence` and `notes` changed |
| `2a63683` | the overall sentence reads as a list ("confirmed by the README text and source …"); `launch/summarize.py` keeps the overall status apart from the comparisons (`licence_overall`, `licence_overall_sub`); `eval/holdout_subsets.py` (exploratory subsets) |
| the commit of this entry | held-out results, v2 launch results, RESULTS / README / LAUNCH / PLAN, demo GIF and cast |

### Labels: AI first pass against the final labels

ChatGPT made a first pass (`classified_review.csv`, keyed by `hf_id`); the owner then checked every row against the frozen cards and corrected it.
- **`expected_status` changed in 12 of 120 rows, and `expert_licences` in the same 12.** `confidence` changed in 33 (the first pass marked 8 rows `sure`, the final labels 37).
- 108 of the first pass's notes mention a current or latest card; the final labels use only the frozen copies.
- Of the 64 scored rows, 60 equal the first pass and 4 were changed.
- Status changes (first pass → final):

  | change | rows |
  |---|---|
  | card unreadable → expert none | 4 |
  | card unreadable → consistent | 2 |
  | card unreadable → inconsistent | 1 |
  | card unreadable → non-SPDX | 1 |
  | non-SPDX → consistent | 1 |
  | consistent → non-SPDX | 1 |
  | missing → expert none | 1 |
  | missing → card unreadable | 1 |

### Held-out score (`eval/results/holdout/`)

- **Prediction run:** `predict.py` from the ScanCode venv in PowerShell, 2026-11-22 18:10 to 22:58 (+04:00). The first attempt refused: an untracked `eval/holdout/cards.zip` (the owner's archive of the card copies) sat under the frozen paths. It is now git-ignored, like `cards/`.
- **Rows:** 64 scored (54 consistent, 6 inconsistent, 4 missing); no batch b needed.

| part of the goal | result |
|---|---|
| kappa ≥ 0.61 | met, 0.626 (bootstrap 0.28–0.87) |
| abstention < 15% | met, 9.4% (Wilson upper bound 19.0%) |
| beats B | met: 34 against 5, p = 2.4e-6 |
| beats A | **missed**: 2 against 8, p = 0.11 |

**The goal was missed.** The tag alone agrees on 58 of 64 rows, datasetvet on 52, ScanCode alone on 23.
- **Sure subset (exploratory):** 26 rows; A 24, B 18, C 23; C kappa 0.84 against A 0.64; C vs A p = 1.0.
- **The 8 rows only the tag gets right:**
  - 2 from licence files of Python packages vendored in a committed `.venv`;
  - 2 from a source repo's `LICENSE` where the code-licence rule does not apply;
  - 1 from an asset folder's `LICENSE`;
  - 1 from `.py` files whose names contain "license";
  - 2 from README text the matcher did not identify, or named without a version.
  - These are on the new v0.2 list (PLAN §11).

**Deviations from the pre-registration**, written into RESULTS §1:
1. AI in the label step.
2. 24 no-README repos labelled `card unreadable` instead of by `LABELLING.md`. All three configurations say `missing` on all 24. A sensitivity check counting them as `missing` leaves the outcome unchanged: A 82, C 76, B 47 of 88, and C vs A still 2 against 8.
3. The subsets were added after labelling.

### v2 launch re-run (Tier A)

- **Run:** all 500 with `2a63683` (config hash `14b429ea97a2357a`), 3 shards, 2026-11-22 18:26 to 23:43 (+04:00). 48,898 s of checking and 25,493 requests, against 6,602 requests for v1, because every cut-off file list is now paged.
- **Speed:** shard 0 drew most of the very large repos (single datasets took up to 42 minutes). It sped up once the held-out predictions stopped sharing the anonymous rate limit.
- **Results:** 497 done, 3 gone.
  - Card licence missing: 182 (36.6%; 32.5–40.9%).
  - Overall status for the 315 cards with a licence: confirmed 132, uncontradicted 82, differs 20, card unclear 64, unresolved 17.
  - Datasets with a dead link: 18 of 172.
- **Problem found: the v1 headline was wrong.** Comparing the v1 and v2 tables, 18 datasets moved from "no README.md at this revision" to a stated licence at the same sha.
  - All 18 are among the 128 repos with a file list cut at 100,000 entries that Phase 4.5 did not rescan. The first scan looked for `README.md` in the cut list.
  - Phase 4.5's note said only a licence file past the cut-off could change those rows. That was wrong: the README could too.
  - So "40.1% state no licence" was too high; the corrected figure is 36.6%. The owner approved it as the headline.
  - The held-out sheet was not affected: it fetched each README directly. Three of the 18 are in it, and their cards were read.
- Tier B (data health) does not depend on the licence rules and was not re-run.

### Docs

- **RESULTS.md**, restructured:
  - headline: what the tag can't show, then accuracy on both keys side by side;
  - §1 held-out (goal, labels with the exact wording, the label-change counts, deviations, tables, subsets);
  - §2 DPI key (v2, no longer blind);
  - §3 launch scan (v2 Tier A, and the 40.1% → 36.6% correction under "What earlier scans got wrong");
  - §4 limits, including the label line and contradiction recall;
  - §5 the v1 results, marked superseded and kept as the record.
- **README:** opens with the checks the tag can't do. The launch table and the accuracy section are v2 only, and the accuracy section says plainly that the status is no better than the tag alone as a yes/no. Two new limits; the sample excerpt shows the new sentence.
- **LAUNCH.md:** rewritten with v2 numbers, leading with 36.6%. Every post says the licence status did not beat the tag, and describes the labels with the exact wording.
- **Demo:** re-recorded with `tools/record_demo.py`, a real uncached run of `check hf:tatsu-lab/alpaca` (12 s), v2 output. pyte and Pillow were installed in a throwaway venv in the session scratchpad, not in the project venvs.
- **PLAN.md:** status line, the Phase 5.5 status, and a v0.2 list (contradiction recall first; vendored-package licence files; source files named like licences; asset-folder licences; a new held-out set labelled by someone else).

### Problems found and fixed

1. `cards.zip` under the frozen paths blocked `predict.py` (above); git-ignored.
2. The first `predict.py` log was written as UTF-16 by PowerShell's `>` and was unreadable to the tools; re-run with `Out-File -Encoding utf8`.
3. With the uncontradicted rule switched off, the new sentence join failed on an empty list (`IndexError`) in a rule-variant test; it now handles empty and one-item lists.
4. The v1 launch headline (above).

### Not done / open

- The two Phase 4 disagreement samples (v1) are still unlabelled.
- The three new missing-file results (`3dcodeverse/3dcodeverse-2m`, `zdbfv/M3_VOS`, `HenryYHW/ADAS-TO`) were not checked by hand.
- The v0.2 list (PLAN §11).

**Checks** (before the commit of this entry): `pytest` 434 passed, 4 skipped (ScanCode-only), 2 deselected; in the ScanCode venv `tests/test_scancode.py` and `tests/test_licence_rules_v2.py`: 31 passed, 1 skipped; `ruff check src tests tools eval launch` clean; `mypy src` clean.
