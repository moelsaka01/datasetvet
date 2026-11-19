# Draft issue for github.com/spdx/license-list-data

Status: draft for the owner to post. Not posted.

---

**Title:** What licence covers the data in this repository?

Hello, and thank you for maintaining the licence list.

I am building an open-source (MIT) tool that checks dataset licences, and I would like to reuse data from this repository correctly. I could not find which licence applies to it:

- GitHub detects no licence for this repository (the API's `license` field is empty), and there is no LICENSE file at the root.
- README.md, CONTRIBUTING.md and accessingLicenses.md do not say.
- The footer of spdx.org/licenses says "© 2018 SPDX Workgroup a Linux Foundation Project. All Rights Reserved".

Could you say which terms apply to:

1. the list metadata in `json/licenses.json` (ids, names, OSI/FSF flags, `seeAlso` URLs), and
2. the licence texts in `text/` (I understand each licence text may have its own terms, but the files here are SPDX's versions of them)?

What I do now: my package ships only (1)-style metadata and a hashed fingerprint index derived from the texts in `text/`. It contains no readable licence text, and a build script regenerates it from a pinned tag of this repository. If a licence (for example CC0-1.0 or CC-BY-3.0) applies, I will add the attribution it requires.

Thank you.
