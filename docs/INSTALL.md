# Installing datasetvet

Python 3.11 or newer.

## Plain install (built-in licence matcher)

```powershell
python -m pip install datasetvet
```

This includes the built-in licence matcher: deterministic, no AI, standard library only, matching
against the official SPDX licence texts that ship with the package (SPDX licence list 3.29.0,
92 texts in 87 groups). It recognises full licence texts (LICENSE files, a licence pasted
into a README), licence names and ids in licence statements ("released under CC BY-NC 4.0",
"License: MIT"), `SPDX-License-Identifier:` lines and licence URLs (creativecommons.org,
opensource.org and the other URLs the SPDX list publishes). It does not recognise licences
that are not on the SPDX list (Llama, OpenRAIL, custom terms).

## Optional: ScanCode (`[scan]` extra)

```powershell
python -m pip install "datasetvet[scan]"
datasetvet check hf:org/name --scanner scancode
```

ScanCode toolkit detects many more licences and notices, at a cost: about 650 MB installed.
`--scanner auto` (the default) uses ScanCode when it is installed and the built-in matcher
otherwise; every report names the scanner it used.

### Windows

Measured on Windows 11 with Python 3.12 (PLAN.md section 9):

1. **Use a short venv path.** ScanCode's licence rules have long file names, and pip fails
   with `OSError: No such file or directory ... .RULE` under a long path unless Windows long
   paths are enabled. A venv at a short path works:

   ```powershell
   py -3.12 -m venv C:\dv
   ```

   ```powershell
   C:\dv\Scripts\python.exe -m pip install "datasetvet[scan]"
   ```

2. **The extra pins `pluggy<1.6`** (pluggy 1.7 breaks ScanCode's plugin loading on import) and
   **adds `typecode-libmagic`** on Windows (the `-mini` package ships no libmagic). Both are
   installed for you by the extra. Do not install pytest 9 or later into the same venv: it
   needs pluggy 1.6+ and breaks ScanCode again (use `pytest<9` there).

3. **Run from PowerShell, not Git Bash.** Under Git Bash, ScanCode finds Git's own libmagic and
   crashes.

## Tokens

Nothing is required. When present in your own environment:

- a Hugging Face login (`hf auth login` or `HF_TOKEN`) raises the Hub's rate limits;
- `GITHUB_TOKEN` adds GitHub's own detected licence (licensee) for GitHub sources, labelled
  as GitHub's.

datasetvet never asks for, prints, logs or stores a token; reports say only whether one was used.
