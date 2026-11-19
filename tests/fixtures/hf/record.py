"""Re-record the offline Hugging Face fixtures (anonymous, free endpoints only).

    python tests/fixtures/hf/record.py

Each dataset gets a folder with the raw JSON responses the adapter reads. README.md files are
cut to their YAML front matter (metadata only), so no card prose is copied into this repo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx2

HERE = Path(__file__).parent
DATASETS = {
    "imdb": "stanfordnlp/imdb",  # Parquet conversion, ClassLabel, 3 splits
    "hle": "cais/hle",  # gated (auto)
    "simready": "nvidia/simready-assets",  # Dataset Viewer disabled: no conversion
}


def front_matter(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "".join(lines[: i + 1])
    return ""


def main() -> int:
    c = httpx2.Client(timeout=30, follow_redirects=True,
                      headers={"user-agent": "datasetvet-fixture-recorder"})
    for name, ds in DATASETS.items():
        d = HERE / name
        d.mkdir(exist_ok=True)
        info = c.get(f"https://huggingface.co/api/datasets/{ds}", params={"blobs": "true"})
        info_json = info.json()
        info_json["siblings"] = info_json.get("siblings", [])[:60]
        (d / "info.json").write_text(json.dumps(info_json, indent=1), "utf-8")
        sha = info_json["sha"]
        readme = c.get(f"https://huggingface.co/datasets/{ds}/resolve/{sha}/README.md")
        (d / "readme_status.txt").write_text(str(readme.status_code), "utf-8")
        if readme.status_code == 200:
            (d / "README.md").write_text(front_matter(readme.text), "utf-8")
        for ep in ("parquet", "size"):
            r = c.get(f"https://datasets-server.huggingface.co/{ep}", params={"dataset": ds})
            (d / f"{ep}.json").write_text(json.dumps({"status": r.status_code,
                                                      "body": r.json()}, indent=1), "utf-8")
        refs = c.get(f"https://huggingface.co/api/datasets/{ds}/refs")
        (d / "refs.json").write_text(json.dumps({"status": refs.status_code,
                                                 "body": refs.json()}, indent=1), "utf-8")
        print(name, ds, sha, "README", readme.status_code)
    return 0


if __name__ == "__main__":
    sys.exit(main())
