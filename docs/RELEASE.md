# Release checklist (nothing here has been run)

Creating the GitHub repo, pushing and publishing to PyPI are the owner's calls. Log in yourself (`gh auth login`, a PyPI token or trusted publishing); nothing in this project asks for or stores a token.

## What is ready

- Package: `datasetvet` 0.1.0. `python -m build` and `twine check` pass on both the sdist and the wheel (BUILD_LOG, Phase 5). A clean-venv install of the wheel runs `datasetvet check`.
- Action: `action.yml`, `examples/workflow.yml`, and `.github/workflows/action-test.yml` (runs the Action on this repo's own checkout once it is on GitHub).
- README, RESULTS.md, LAUNCH.md (post drafts).

## GitHub repo (description and topics, for `gh repo create` / `gh repo edit`)

Repo name: `datasetvet` (assumed owner `moelsaka01`, from the local git user; the README and `pyproject.toml` URLs use it, so change them if the owner differs).

Description (under 350 characters):

> Before you train on it, check it. A CLI that checks a Hugging Face dataset and writes a report of verifiable facts: licence consistency, provenance, dead links, duplicates, leakage. Facts only, not legal advice.

Topics: `dataset`, `huggingface`, `licenses`, `data-quality`, `data-validation`, `provenance`, `machine-learning`, `mlops`, `cli`, `github-action`

## Commands, in order (run them yourself after you have read the checklist)

```powershell
gh auth status
gh repo create datasetvet --public --description "Before you train on it, check it. A CLI that checks a Hugging Face dataset and writes a report of verifiable facts: licence consistency, provenance, dead links, duplicates, leakage. Facts only, not legal advice." --source . --remote origin
gh repo edit --add-topic dataset --add-topic huggingface --add-topic licenses --add-topic data-quality --add-topic data-validation --add-topic provenance --add-topic machine-learning --add-topic mlops --add-topic cli --add-topic github-action
git push -u origin main
git push origin eval-config-v1
```

Then, once CI is green on the first push:

```powershell
git tag v0.1.0
git push origin v0.1.0
git tag -f v0
git push -f origin v0
```

(`v0` is the moving tag the README's `uses: ...@v0` points at.)

## Before the first push

- **The backup bundle still holds the SPDX licence texts** (`C:/Users/melsa/datasetvet-backups/`, BUILD_LOG Phase 4.5). Keep it outside the repo and do not upload it; delete it after the first push if you no longer need it.
- **CI has never run** (both jobs, plus `action-test`). Expect to fix small things on the first push; the Python 3.11 and 3.13 legs have not been run locally.
- **The SPDX issue** (`docs/drafts/spdx-license-list-data-issue.md`) is still unposted.
- The tag `eval-config-v1` is local; `eval/run.py` refuses the test split unless it exists.
- Check that `launch/state.sqlite` and `launch/results/reports*/` are still untracked (`git ls-files launch`).

## PyPI (build and check only; you upload)

```powershell
python -m pip install build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*     # you log in; the name datasetvet was free on 2026-11-19, re-check first
```

Check the name again just before uploading (`https://pypi.org/project/datasetvet/` should be a 404): names are first come, first served.
