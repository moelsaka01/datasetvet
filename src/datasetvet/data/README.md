# data

Tables used by the checks. Every row carries its source.

| file | what | source |
|---|---|---|
| `hf_licence_ids.csv` | all 83 ids on HF's licence list -> SPDX id / family / non-SPDX / special (task 3.1) | `source` column: hub-docs `repositories-licenses.md` at commit `fd6cf1f` |
| `spdx_licences.json.gz` | 92 official SPDX licence texts for the built-in matcher, plus name, OSI/FSF/deprecated flags and `seeAlso` URLs; flags for all 740 ids | `spdx/license-list-data` tag v3.29.0; rebuilt by `tools/vendor_spdx.py` |
| `cc_elements.csv` | Creative Commons elements (BY/SA/NC/ND) for the 53 CC licences on the SPDX list, with each deed URL (task 3.3) | `deed_url` column (creativecommons.org); generated from the SPDX list's `seeAlso` URLs |

The SPDX licence list does not state a licence for its own data (PLAN.md section 12).
