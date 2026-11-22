# Held-out labelling sheet (`holdout-v1`)

Pre-registered in [PLAN.md §8.1](../../PLAN.md#81-phase-55-held-out-evaluation-pre-registered-2026-11-22). 120 datasets drawn at random (seed 20261122) from the launch list (`launch/lists/top500-2026-11-19.json`) after removing every repo the DPI collection names. Each is pinned to the sha frozen on 2026-11-19. How they were drawn: `eval/holdout/draw.py`, `eval/holdout/draw-a.json`.

## Keep it blind

- Do **not** run datasetvet on these datasets, and do not open `launch/results/` (CSV, reports, summaries) for them, until every row is labelled.
- The sheet holds no datasetvet output: only the card's own YAML licence fields (copied verbatim), the URLs written in the card, pinned links and the Hub's gated flag.
- `eval/holdout/cards/` (on this laptop only, not committed) has each readable card as it was at the frozen sha; `card_sha256` in the sheet matches those bytes.

## What to fill in

Four columns per row. Leave none of `expert_licences` and `expected_status` empty.

| column | what to write |
|---|---|
| `expert_licences` | The licence(s) under which **the dataset (the data)** is released, as you conclude from the card, the repo's licence files and the original source (paper, homepage, GitHub repo), the way the DPI audit did. SPDX ids separated by `;` (e.g. `CC-BY-4.0` or `CC-BY-SA-4.0;MIT`). For a licence not on the SPDX list write `non-SPDX: <name>` (custom terms, Llama/Gemma licences, OpenRAIL, a provider's terms of use, "research only", "non-commercial" without a named licence). If nothing states a licence for the data, write `none`. |
| `expected_status` | One of the six values below, decided **in this order** (the DPI rules in `eval/build_key.py`). |
| `confidence` | `sure` or `unsure`. |
| `notes` | Optional: what decided it, e.g. "repo LICENSE is for the code; card and paper say CC-BY-4.0". |

`expected_status`, first rule that applies:

1. any expert licence is `non-SPDX` → `excluded: expert non-SPDX`
2. expert licence is `none` → `excluded: expert none`
3. the card's YAML `license` is absent, empty or `unknown` → `missing`
4. the card's YAML `license` is not one SPDX licence (`other`, a family id such as `cc`, `bsd`, `gpl`, `openrail`, or a non-SPDX id such as `llama2`) → `excluded: card non-SPDX`
5. the card's licence(s) equal the expert set (a YAML list counts as all of its members) → `consistent`
6. otherwise → `inconsistent`

## Rows that cannot be read

- `card_note` says when the README was not readable anonymously (gated repos): the YAML fields then come from the Hub API. Log in on the Hub to read the card if you can; label as usual.
- If the card cannot be fetched at all at the frozen sha, label `excluded: card unreadable`.

When every row is labelled, commit the sheet. Then, from the ScanCode venv in PowerShell: `python eval/holdout/predict.py` (refuses while any `expected_status` is empty, when a column other than the four label columns changed since `holdout-v1`, or when the code differs from `eval-config-v2`), then `python eval/holdout/score.py`. No prediction is made before the sheet is fully labelled.
