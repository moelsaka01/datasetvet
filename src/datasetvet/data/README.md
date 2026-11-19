# data

Tables used by the checks. Every row carries its source.

| file | what | source |
|---|---|---|
| `hf_licence_ids.csv` | all 83 ids on HF's licence list -> SPDX id / family / non-SPDX / special (task 3.1) | `source` column: hub-docs `repositories-licenses.md` at commit `fd6cf1f` |
| `spdx_licences.json.gz` | SPDX licence list metadata only: name, OSI/FSF/deprecated flags and `seeAlso` URLs for the 92 licences the matcher indexes, plus flags for all 740 ids. **No licence text** | `spdx/license-list-data` tag v3.29.0; rebuilt by `tools/vendor_spdx.py` |
| `spdx_fingerprints.json.gz` | the built-in matcher's index: for each of 87 distinct texts (92 ids), the multiset of 64-bit BLAKE2b hashes of its normalised word bigrams, and its word count. **No licence text**: words are not stored | derived from the same tag's `text/<id>.txt` by `tools/vendor_spdx.py`; `--check` rebuilds it byte for byte |
| `cc_elements.csv` | Creative Commons elements (BY/SA/NC/ND) for the 53 CC licences on the SPDX list, with each deed URL (task 3.3) | `deed_url` column (creativecommons.org); generated from the SPDX list's `seeAlso` URLs |

The SPDX licence list does not state a licence for its own data (PLAN.md section 12), so the licence texts are not shipped or committed. `python tools/vendor_spdx.py` downloads them to `.datasetvet-cache/spdx/<tag>/` (git-ignored) and regenerates both SPDX files; the tests that need real licence texts read that folder and are skipped without it.
