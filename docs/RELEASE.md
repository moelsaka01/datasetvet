# Release checklist

Publishing to PyPI and creating releases are the owner's calls. Nothing in this project asks for or stores a token: PyPI publishing uses **trusted publishing** (GitHub's OIDC), so no PyPI token exists at all.

## Done (2026-11-23)

- GitHub repo `moelsaka01/datasetvet`, public, with the description and topics below. `main` and the tags `eval-config-v1`, `eval-config-v2` and `holdout-v1` are pushed.
- CI is green on `main` (6 test legs, `scan-windows`, `action-test`). The runs on the three frozen tags are red: they predate the fix to the SPDX index check, and the tags are not moved.
- `python -m build` and `twine check --strict` pass on the sdist and the wheel. The name `datasetvet` was free on PyPI on 2026-11-23 (`https://pypi.org/pypi/datasetvet/json` returned 404).

## GitHub repo (description and topics)

Description:

> Before you train on it, check it. A CLI that checks a Hugging Face dataset and writes a report of verifiable facts: licence consistency, provenance, dead links, duplicates, leakage. Facts only, not legal advice.

Topics: `dataset`, `huggingface`, `licenses`, `data-quality`, `data-validation`, `provenance`, `machine-learning`, `mlops`, `cli`, `github-action`

## Publishing 0.1.0 to PyPI (trusted publishing)

`.github/workflows/release.yml` runs when a GitHub release is **published**. It:
- builds the sdist and wheel;
- runs `twine check --strict`;
- checks that the tag equals `v` + the version in `pyproject.toml`;
- installs the wheel in a clean venv and runs `datasetvet --help`;
- uploads to PyPI from the `pypi` environment, with `id-token: write` as its only permission.

1. **Owner, on pypi.org** (logged in, with 2FA): Account settings → Publishing → *Add a new pending publisher* → GitHub, with:
   - PyPI project name: `datasetvet`
   - Owner: `moelsaka01`
   - Repository name: `datasetvet`
   - Workflow name: `release.yml`
   - Environment name: `pypi`

   A pending publisher does not reserve the name. Create the release soon after.
2. **Optional, on GitHub:** Settings → Environments → `pypi` → *Required reviewers*: add yourself, so every publish waits for your click. The workflow creates the environment on its first run if it does not exist.
3. **Create the release** (tag `v0.1.0` on `main`):

   ```powershell
   gh release create v0.1.0 --target main --title "datasetvet 0.1.0" --notes-file docs/release-notes-0.1.0.md
   ```

   Publishing the release starts `release.yml`, and that uploads to PyPI. Attach nothing: `launch-state-v0.1.zip` stays private.
4. **Check:** the `release` run is green, `https://pypi.org/project/datasetvet/0.1.0/` exists, and a clean venv can run `pip install datasetvet` and `datasetvet check hf:stanfordnlp/imdb --no-data`.
5. **The Action tag:** `git tag -f v0 v0.1.0`, then `git push -f origin v0`. `v0` is the moving tag the README's `uses: moelsaka01/datasetvet@v0` points at.

If the upload fails (for example, the pending publisher is missing), fix it on PyPI and re-run the failed `publish` job from the Actions tab. A failed upload does not consume the version number. Never re-use a version that was actually uploaded.

## Still open

- **The backup bundle holds the SPDX licence texts** (`~/datasetvet-backups/`, now also inside `~/datasetvet-archive/private-keep.zip`). Never upload it.
- **The SPDX issue** (`docs/drafts/spdx-license-list-data-issue.md`) is still unposted.
- `launch/state.sqlite` and `launch/results/reports*/` stay untracked (`git ls-files launch`); `launch-state-v0.1.zip` is private and is not attached to any release.
