"""Email and phone pattern matches, masked examples (PLAN.md 5.5). Task 2.11.

String columns only. These are *pattern matches*, not a finding that the data contains
personal data. Examples are always masked; the full value is never printed.

- Email: an RFC 5322-lite pattern. The domain needs a letters-only top-level label of 2+
  characters, so `pkg@1.2.3` and `user@localhost` do not match; image-name suffixes such as
  `icon@2x.png` are excluded.
- Phone: international `+` candidates validated with `phonenumbers`. With a region
  (`--phone-region GB`), national formats for that region are matched as well.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

import phonenumbers
import pyarrow as pa
import pyarrow.compute as pc

EXAMPLES = 3

EMAIL_RE = re.compile(
    r"(?<![\w.%+-])([A-Za-z0-9](?:[A-Za-z0-9._%+-]{0,62}[A-Za-z0-9_%+-])?)@"
    r"((?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+([A-Za-z]{2,24}))(?![\w-])"
)
_FILE_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico", "tif", "tiff", "avif"}
PHONE_CANDIDATE_RE = re.compile(r"(?<![\w+])\+\d[\d\s().\-]{6,20}\d(?!\d)")


def find_emails(text: str) -> list[str]:
    out = []
    for m in EMAIL_RE.finditer(text):
        if m.group(3).lower() in _FILE_TLDS:
            continue
        out.append(m.group(0))
    return out


def find_phones(text: str, region: str | None = None) -> list[str]:
    out = []
    for m in PHONE_CANDIDATE_RE.finditer(text):
        cand = m.group(0)
        try:
            num = phonenumbers.parse(cand, None)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(num):
            out.append(cand)
    if region:
        seen = set(out)
        for match in phonenumbers.PhoneNumberMatcher(text, region,
                                                     leniency=phonenumbers.Leniency.VALID):
            if match.raw_string not in seen and not match.raw_string.startswith("+"):
                out.append(match.raw_string)
    return out


def mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    labels = domain.split(".")
    tld = labels[-1]
    host = labels[0] if labels else ""
    return f"{local[:1]}***@{host[:1]}***.{tld}"


def mask_phone(value: str) -> str:
    digits = [i for i, ch in enumerate(value) if ch.isdigit()]
    keep = set(digits[-2:])
    return "".join("*" if ch.isdigit() and i not in keep else ch for i, ch in enumerate(value))


@dataclass
class ColumnMatches:
    values_with_email: int = 0
    values_with_phone: int = 0
    email_examples: list[str] = field(default_factory=list)
    phone_examples: list[str] = field(default_factory=list)


@dataclass
class PiiScanner:
    region: str | None = None
    columns: dict[str, ColumnMatches] = field(default_factory=dict)
    values_scanned: int = 0

    def add(self, name: str, arr: pa.Array | pa.ChunkedArray) -> None:
        if not (pa.types.is_string(arr.type) or pa.types.is_large_string(arr.type)):
            return
        col = self.columns.setdefault(name, ColumnMatches())
        self.values_scanned += len(arr) - arr.null_count
        # cheap vectorised prefilters before any Python regex
        has_at = pc.fill_null(pc.match_substring(arr, "@"), False)
        if pc.any(has_at).as_py():
            for v in pc.filter(arr, has_at).to_pylist():
                hits = find_emails(v)
                if hits:
                    col.values_with_email += 1
                    if len(col.email_examples) < EXAMPLES:
                        col.email_examples.append(mask_email(hits[0]))
        if self.region:
            cand = pc.fill_null(pc.match_substring_regex(arr, r"\d.*\d.*\d.*\d.*\d.*\d"), False)
        else:
            cand = pc.fill_null(pc.match_substring_regex(arr, r"\+\d"), False)
        if pc.any(cand).as_py():
            for v in pc.filter(arr, cand).to_pylist():
                hits = find_phones(v, self.region)
                if hits:
                    col.values_with_phone += 1
                    if len(col.phone_examples) < EXAMPLES:
                        col.phone_examples.append(mask_phone(hits[0]))

    def scanned_columns(self) -> list[str]:
        return list(self.columns)

    def any_found(self) -> bool:
        return any(c.values_with_email or c.values_with_phone for c in self.columns.values())


def string_columns(schema: pa.Schema) -> Iterable[str]:
    for f in schema:
        if pa.types.is_string(f.type) or pa.types.is_large_string(f.type):
            yield f.name
