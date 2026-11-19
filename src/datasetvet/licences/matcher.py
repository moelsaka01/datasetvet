"""Built-in licence matcher: deterministic, no AI, standard library only (PLAN.md section 4).

Three detectors, all against the vendored SPDX licence list (`spdx.spdx_data()`):

1. **Full text** (askalono-style). Text is normalised along the lines of the SPDX matching
   guidelines (case, punctuation, quotes, dashes, bullets, copyright lines, SPDX's
   equivalent words), split into words, and compared as sets of word bigrams:
   - `dice` = 2|A∩B| / (|A|+|B|): the file *is* licence B when dice >= DICE_MIN;
   - `containment` = |A∩B| / |B|: the file *contains* licence B (e.g. a README with the MIT
     text under "## License") when containment >= CONTAIN_MIN. When two contained licences
     overlap (MIT inside X11, BSD-2-Clause inside BSD-3-Clause), the larger one wins.
   Bigrams are counted as a multiset, so repeated clauses count. SPDX texts that are
   identical after normalisation (GPL-2.0-only / GPL-2.0-or-later) form one group, and a detection lists every id in its group.
2. **Notices**: `SPDX-License-Identifier:` lines, and licence names or ids from the SPDX list
   (plus common short forms such as "CC BY-NC 4.0", "Apache 2.0", "GPLv3") inside a licence
   context: a "License:" line, a section headed License/Licensing, or within a few words of
   the word license/licence. One-word names (MIT, ISC, ...) need the word license next to them.
3. **Licence URLs**: creativecommons.org licence/deed URLs, and the `seeAlso` URLs the SPDX
   list publishes for each licence (opensource.org, apache.org, gnu.org, ...).

Thresholds are fixed here and may only be tuned on the Phase 4 dev split.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import pairwise

from datasetvet.licences import spdx

DICE_MIN = 0.90
CONTAIN_MIN = 0.95
MIN_TEXT_BIGRAMS = 20  # licences shorter than this are matched as notices only
NEAR_WORDS = 25  # a multi-word licence name counts within this many words of "license"
NEAR_WORDS_SHORT = 3  # a one-word name (MIT, ISC) needs "license" this close

# SPDX's equivalentwords.txt (license-list-XML v3.29.0), applied after lower-casing
EQUIVALENT_WORDS = {
    "acknowledgment": "acknowledgement", "analogue": "analog", "&": "and",
    "analyse": "analyze", "artefact": "artifact", "authorisation": "authorization",
    "authorised": "authorized", "calibre": "caliber", "cancelled": "canceled",
    "capitalisations": "capitalizations", "catalogue": "catalog", "categorise": "categorize",
    "centre": "center", "emphasised": "emphasized", "favour": "favor",
    "favourite": "favorite", "fulfil": "fulfill", "fulfilment": "fulfillment",
    "initialise": "initialize", "judgement": "judgment", "labelling": "labeling",
    "labour": "labor", "licence": "license", "maximise": "maximize",
    "modelled": "modeled", "modelling": "modeling", "offence": "offense",
    "optimise": "optimize", "organisation": "organization", "organise": "organize",
    "practise": "practice", "programme": "program", "realise": "realize",
    "recognise": "recognize", "signalling": "signaling", "sub-license": "sublicense",
    "sub license": "sublicense", "utilisation": "utilization", "whilst": "while",
    "wilful": "willful", "non-commercial": "noncommercial", "per cent": "percent",
    "copyright owner": "copyright holder",
}
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                         "–": "-", "—": "-", "−": "-", " ": " "})
_TOKEN_RE = re.compile(r"[a-z]+|[0-9]+")
_COPYRIGHT_RE = re.compile(r"^\s*(copyright\b|\(c\)|©).*$", re.IGNORECASE | re.MULTILINE)
_URL_RE = re.compile(r"https?://[^\s<>\"'\)\]\}`|]+", re.IGNORECASE)
_UNDER_VERBS = {"released", "distributed", "available", "published", "provided", "shared",
                "licensed", "licenced", "offered", "covered", "governed"}
_LICENSE_WORDS = {"license", "licenses", "licensed", "licensing", "licence", "licences",
                  "licenced", "licencing"}


@dataclass
class Detection:
    """One licence found in a text. `expression` is an SPDX expression or a LicenseRef."""

    expression: str
    method: str  # "full text", "contains text", "SPDX-License-Identifier", "name", "URL"
    score: float | None  # 0-100 for text similarity; None for exact name/URL matches
    lines: tuple[int, int] | None = None
    matched: str = ""  # the matched words or URL, shortened
    alternatives: list[str] = field(default_factory=list)  # same text, other SPDX ids
    versionless: bool = False  # e.g. "CC BY-NC" without a version: not one licence

    def describe(self) -> str:
        how = self.method
        if self.score is not None:
            how += f", score {self.score:.0f}"
        if self.lines:
            a, b = self.lines
            how += f", line {a}" if a == b else f", lines {a}-{b}"
        return how

    def as_dict(self) -> dict[str, object]:
        return {"expression": self.expression, "method": self.method, "score": self.score,
                "lines": list(self.lines) if self.lines else None, "matched": self.matched,
                "alternatives": self.alternatives, "versionless": self.versionless}


# -- normalisation ---------------------------------------------------------------------------

def _prep(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).translate(_QUOTES).lower()
    t = _COPYRIGHT_RE.sub(" ", t)
    for a, b in EQUIVALENT_WORDS.items():
        if " " in a or "-" in a or a == "&":
            t = t.replace(a, f" {b} ")
    return t


def words(text: str) -> list[str]:
    toks = _TOKEN_RE.findall(_prep(text))
    return [EQUIVALENT_WORDS.get(w, w) for w in toks]


def bigrams(toks: list[str]) -> Counter[tuple[str, str]]:
    """Word bigrams with their counts (a multiset, so repeated clauses count)."""
    return Counter(pairwise(toks))


def _overlap(a: Counter[tuple[str, str]], b: Counter[tuple[str, str]]) -> int:
    if len(a) > len(b):
        a, b = b, a
    return sum(min(n, b[g]) for g, n in a.items() if g in b)


@dataclass
class _Licence:
    ids: list[str]  # first is the representative
    grams: Counter[tuple[str, str]]
    size: int  # total bigrams
    n_words: int


@lru_cache(maxsize=1)
def _index() -> list[_Licence]:
    out: list[_Licence] = []
    seen: dict[tuple[str, ...], _Licence] = {}
    for lid, meta in sorted(spdx.spdx_data()["licences"].items()):
        toks = words(meta["text"])
        same = seen.get(tuple(toks))
        if same is not None:  # identical normalised text, e.g. GPL-2.0-only / -or-later
            same.ids.append(lid)
            continue
        grams = bigrams(toks)
        lic = _Licence([lid], grams, sum(grams.values()), len(toks))
        seen[tuple(toks)] = lic
        out.append(lic)
    for lic in out:
        lic.ids.sort(key=_prefer)
    return out


def _prefer(lid: str) -> tuple[int, str]:
    # within a group of identical texts, name the -only variant first
    return (0 if lid.endswith("-only") else 1, lid)


def dice(a: Counter[tuple[str, str]], b: Counter[tuple[str, str]]) -> float:
    na, nb = sum(a.values()), sum(b.values())
    return 2 * _overlap(a, b) / (na + nb) if na and nb else 0.0


# -- 1. full text ----------------------------------------------------------------------------

def _token_lines(text: str) -> tuple[list[str], list[int]]:
    toks: list[str] = []
    lines: list[int] = []
    for n, line in enumerate(text.splitlines(), start=1):
        for w in words(line):
            toks.append(w)
            lines.append(n)
    return toks, lines


def _span(toks: list[str], lines: list[int], grams: Counter[tuple[str, str]],
          width: int) -> tuple[int, int]:
    """Line range of the window of `width` words holding the most of the licence's bigrams."""
    hits = [1 if (toks[i], toks[i + 1]) in grams else 0 for i in range(len(toks) - 1)]
    if not hits:
        return (lines[0], lines[0]) if lines else (1, 1)
    width = max(1, min(width, len(hits)))
    best = cur = sum(hits[:width])
    start = 0
    for i in range(width, len(hits)):
        cur += hits[i] - hits[i - width]
        if cur > best:
            best, start = cur, i - width + 1
    idx = [i for i in range(start, start + width) if hits[i]]
    a, b = (idx[0], idx[-1] + 1) if idx else (start, start + width)
    return lines[a], lines[min(b, len(lines) - 1)]


def match_full_text(text: str) -> list[Detection]:
    toks, lines = _token_lines(text)
    doc = bigrams(toks)
    n_doc = sum(doc.values())
    if not n_doc:
        return []
    scored = []
    for lic in _index():
        inter = _overlap(doc, lic.grams)
        if inter:
            scored.append((2 * inter / (n_doc + lic.size), inter / lic.size, lic))
    if not scored:
        return []
    scored.sort(key=lambda x: (-x[0], x[2].ids[0]))
    best_dice, _cont, best = scored[0]
    if best_dice >= DICE_MIN:
        span = _span(toks, lines, best.grams, int(best.n_words * 1.2) + 10)
        return [_text_detection(best, "full text", best_dice, span)]
    contained = [(cont, lic) for _d, cont, lic in scored
                 if cont >= CONTAIN_MIN and lic.size >= MIN_TEXT_BIGRAMS]
    # when one contained licence's text is (almost) inside another contained one, keep the
    # larger: MIT inside X11, BSD-2-Clause inside BSD-3-Clause, 0BSD inside ISC
    keep = [(cont, a) for cont, a in contained
            if not any(b is not a and b.size > a.size
                       and _overlap(a.grams, b.grams) / a.size >= CONTAIN_MIN
                       for _c, b in contained)]
    out = []
    for cont, lic in keep:
        span = _span(toks, lines, lic.grams, int(lic.n_words * 1.2) + 10)
        out.append(_text_detection(lic, "contains text", cont, span))
    return out


def _text_detection(lic: _Licence, method: str, score: float,
                    span: tuple[int, int]) -> Detection:
    return Detection(expression=lic.ids[0], method=method, score=round(score * 100, 1),
                     lines=span, matched=spdx.spdx_data()["licences"][lic.ids[0]]["name"],
                     alternatives=lic.ids[1:])


# -- 2. notices ------------------------------------------------------------------------------

_FILLER = {"the", "version", "v", "international", "unported", "generic", "license", "licence",
           "agreement"}
_CC_EL = {"by": ("attribution",), "nc": ("noncommercial",), "nd": ("noderivatives",),
          "sa": ("sharealike",)}
_JOIN = [  # multi-word spellings folded into one word before alias matching
    (re.compile(r"\bnon[\s-]*commercial\b"), "noncommercial"),
    (re.compile(r"\bno[\s-]*deriv(?:ative)?s?\b"), "noderivatives"),
    (re.compile(r"\bshare[\s-]*alike\b"), "sharealike"),
    (re.compile(r"\b(a|l)?gpl[\s-]*v(\d)"), r"\1gpl \2"),
    (re.compile(r"\bcc0\b"), "cc zero"),
    (re.compile(r"\bcc[\s-]*zero\b"), "cc zero"),
    (re.compile(r"\bcreative[\s-]*commons[\s-]*zero\b"), "cc zero"),
]


def _alias_tokens(text: str) -> tuple[str, ...]:
    t = _prep(text)
    for rx, rep in _JOIN:
        t = rx.sub(rep, t)
    return tuple(w for w in (EQUIVALENT_WORDS.get(x, x) for x in _TOKEN_RE.findall(t))
                 if w not in _FILLER)


@dataclass(frozen=True)
class _Alias:
    expression: str
    versionless: bool = False


def _cc_aliases(lid: str, out: dict[tuple[str, ...], _Alias]) -> None:
    m = re.fullmatch(r"CC-(BY(?:-NC)?(?:-ND|-SA)?)-(\d)\.(\d)", lid)
    if not m:
        return
    els = m.group(1).lower().split("-")
    ver = (m.group(2), m.group(3))
    longw = ("creative", "commons") + tuple(w for e in els for w in _CC_EL[e])
    short = ("cc",) + tuple(els)
    for base in (longw, short, ("creative", "commons") + tuple(els)):
        out[base + ver] = _Alias(lid)
        if m.group(3) == "0":
            out[base + ver[:1]] = _Alias(lid)
        out.setdefault(base, _Alias("CC-" + m.group(1), versionless=True))


_HAND_ALIASES = {
    "GPL-2.0": ["gpl 2", "gpl 2 0", "gnu gpl 2", "gnu gpl 2 0", "gnu general public 2",
                "gnu general public 2 0"],
    "GPL-3.0": ["gpl 3", "gpl 3 0", "gnu gpl 3", "gnu gpl 3 0", "gnu general public 3",
                "gnu general public 3 0"],
    "LGPL-2.1": ["lgpl 2 1", "gnu lgpl 2 1", "gnu lesser general public 2 1"],
    "LGPL-3.0": ["lgpl 3", "lgpl 3 0", "gnu lgpl 3", "gnu lesser general public 3",
                 "gnu lesser general public 3 0"],
    "AGPL-3.0": ["agpl 3", "agpl 3 0", "gnu agpl 3", "gnu affero general public 3",
                 "gnu affero general public 3 0"],
    "Apache-2.0": ["apache 2", "apache 2 0", "asl 2 0"],
    "BSD-3-Clause": ["bsd 3 clause", "3 clause bsd", "new bsd", "revised bsd", "bsd 3"],
    "BSD-2-Clause": ["bsd 2 clause", "2 clause bsd", "simplified bsd", "freebsd", "bsd 2"],
    "MIT": ["mit", "expat"],
    "ODC-By-1.0": ["odc by", "odc by 1 0", "open data commons attribution"],
    "ODbL-1.0": ["odbl", "odbl 1 0", "open database", "open database 1 0"],
    "PDDL-1.0": ["pddl", "pddl 1 0", "open data commons public domain dedication"],
    "CC0-1.0": ["cc zero", "cc zero 1 0", "cc zero universal", "cc zero 1 0 universal"],
    "C-UDA-1.0": ["c uda", "c uda 1 0", "computational use of data"],
    "WTFPL": ["wtfpl"],
    "Unlicense": ["unlicense"],
}


@lru_cache(maxsize=1)
def _aliases() -> dict[tuple[str, ...], _Alias]:
    data = spdx.spdx_data()
    out: dict[tuple[str, ...], _Alias] = {}
    for lid in sorted(set(data["licences"]) | set(data["deprecated"])):
        _cc_aliases(lid, out)
    named = dict(data["deprecated"])
    named.update(data["licences"])  # texted ids win over deprecated ones with the same name
    for lid, meta in named.items():
        for a in (_alias_tokens(lid), _alias_tokens(meta["name"])):
            if a:
                out.setdefault(a, _Alias(lid))
    for lid, forms in _HAND_ALIASES.items():
        for f in forms:
            out[tuple(f.split())] = _Alias(lid)
    return out


@lru_cache(maxsize=1)
def _by_first() -> dict[str, list[tuple[tuple[str, ...], _Alias]]]:
    idx: dict[str, list[tuple[tuple[str, ...], _Alias]]] = {}
    for toks, al in _aliases().items():
        idx.setdefault(toks[0], []).append((toks, al))
    for v in idx.values():
        v.sort(key=lambda x: -len(x[0]))
    return idx


_SPDX_TAG_RE = re.compile(r"SPDX-License-Identifier:\s*([^\n*#>]+)", re.IGNORECASE)
_LICENSE_LINE_RE = re.compile(r"^[\s>*_|#-]*licen[cs](?:e|es|ing)\b[\s*_]*[:：|]",
                              re.IGNORECASE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _licence_lines(lines: list[str]) -> set[int]:
    """1-based numbers of lines that are a licence context of their own: a "License:" line,
    or a line inside a section headed License / Licensing / Licence."""
    out: set[int] = set()
    level = 0
    for n, line in enumerate(lines, start=1):
        h = _HEADING_RE.match(line)
        if h:
            lvl = len(h.group(1))
            if re.search(r"licen[cs]", h.group(2), re.IGNORECASE):
                level = lvl
                out.add(n)
                continue
            if level and lvl <= level:
                level = 0
        if level or _LICENSE_LINE_RE.match(line):
            out.add(n)
    return out


def match_notices(text: str) -> list[Detection]:
    lines = text.splitlines()
    found: list[Detection] = []
    for n, line in enumerate(lines, start=1):
        for m in _SPDX_TAG_RE.finditer(line):
            expr = m.group(1).strip().rstrip(".,;")
            norm = spdx.normalise(expr)
            if norm:
                found.append(Detection(norm, "SPDX-License-Identifier", None, (n, n),
                                       m.group(0)[:120]))
    context_lines = _licence_lines(lines)
    # one token stream over the text without URLs, each token tagged with its line
    toks: list[str] = []
    tok_line: list[int] = []
    raw_words: list[str] = []
    raw_line: list[int] = []
    for n, line in enumerate(lines, start=1):
        clean = _URL_RE.sub(" ", line)
        for w in _alias_tokens(clean):
            toks.append(w)
            tok_line.append(n)
        for w in _TOKEN_RE.findall(_prep(clean)):
            raw_words.append(w)
            raw_line.append(n)
    lic_pos = [i for i, w in enumerate(raw_words) if w in _LICENSE_WORDS
               or (w == "under" and i and raw_words[i - 1] in _UNDER_VERBS)]
    tag_lines = {d.lines[0] for d in found if d.lines}
    by_first = _by_first()
    i = 0
    while i < len(toks):
        hit = None
        for cand, al in by_first.get(toks[i], []):
            if tuple(toks[i:i + len(cand)]) == cand:
                hit = (cand, al)
                break
        if not hit:
            i += 1
            continue
        cand, al = hit
        line_no = tok_line[i]
        if line_no not in tag_lines and _in_context(line_no, cand, raw_words, raw_line, lic_pos, context_lines):
            found.append(Detection(al.expression, "name", None, (line_no, tok_line[i + len(cand)
                                                                                   - 1]),
                                   " ".join(cand), versionless=al.versionless))
        i += len(cand)
    for n, line in enumerate(lines, start=1):
        for u in _URL_RE.findall(line):
            lid = licence_for_url(u)
            if lid:
                found.append(Detection(lid, "URL", None, (n, n), u[:120]))
    return found


def _in_context(line_no: int, cand: tuple[str, ...], raw_words: list[str], raw_line: list[int],
                lic_pos: list[int], context_lines: set[int]) -> bool:
    if line_no in context_lines:
        return True
    near = NEAR_WORDS_SHORT if len(cand) == 1 else NEAR_WORDS
    # positions of this line's words in the raw stream
    on_line = [k for k, ln in enumerate(raw_line) if ln == line_no]
    if not on_line:
        return False
    try:
        k0 = next(k for k in on_line if raw_words[k] == cand[0])
    except StopIteration:
        k0 = on_line[0]
    return any(abs(p - k0) <= near + len(cand) for p in lic_pos)


# -- 3. licence URLs -------------------------------------------------------------------------

_CC_URL_RE = re.compile(
    r"creativecommons\.org/licenses/(by(?:-nc)?(?:-nd|-sa)?)/(\d\.\d)"
    r"(?:/([a-z]{2,3})(?=[/?#]|$))?",
    re.IGNORECASE)
_CC0_URL_RE = re.compile(r"creativecommons\.org/publicdomain/zero/1\.0", re.IGNORECASE)
_GNU_URL_RE = re.compile(r"gnu\.org/licenses/(a|l)?gpl-(\d\.\d)", re.IGNORECASE)
_ODC_URL_RE = re.compile(r"opendatacommons\.org/licenses/(by|odbl|pddl)\b", re.IGNORECASE)
_ID_URL_RE = re.compile(r"(?:spdx\.org/licenses|choosealicense\.com/licenses|"
                        r"opensource\.org/licenses?)/([A-Za-z0-9.+\-]+?)(?:\.html|/|$)",
                        re.IGNORECASE)


def _url_key(u: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", u.strip().lower())
    u = re.sub(r"(legalcode(\.[a-z-]+)?|deed\.[a-z-]+|\.html?|\.txt|\.php)$", "", u)
    return u.rstrip("/#")


@lru_cache(maxsize=1)
def _see_also() -> dict[str, str]:
    data = spdx.spdx_data()
    out: dict[str, str] = {}
    for group in ("deprecated", "licences"):
        for lid, meta in data[group].items():
            for u in meta.get("see_also", []):
                out[_url_key(u)] = lid
    return out


def licence_for_url(url: str) -> str | None:
    """SPDX id whose official URL this is, or None. Not fetched: the URL itself is the fact."""
    m = _CC_URL_RE.search(url)
    if m:
        lid = f"CC-{m.group(1).upper()}-{m.group(2)}"
        if m.group(3):
            ported = spdx.spdx_id(f"{lid}-{m.group(3)}")
            return ported
        return spdx.spdx_id(lid)
    if _CC0_URL_RE.search(url):
        return "CC0-1.0"
    m = _GNU_URL_RE.search(url)
    if m:
        return spdx.spdx_id(f"{(m.group(1) or '').upper()}GPL-{m.group(2)}")
    m = _ODC_URL_RE.search(url)
    if m:
        return {"by": "ODC-By-1.0", "odbl": "ODbL-1.0", "pddl": "PDDL-1.0"}[m.group(1).lower()]
    m = _ID_URL_RE.search(url)
    found = spdx.spdx_id(m.group(1)) if m else None
    return found or _see_also().get(_url_key(url))


# -- all detectors ---------------------------------------------------------------------------

def detect(text: str, *, full_text: bool = True) -> list[Detection]:
    """Every licence found in `text`, deduplicated by expression (best evidence kept)."""
    dets: list[Detection] = match_full_text(text) if full_text else []
    spans = [d.lines for d in dets if d.lines]
    # names and URLs quoted inside a matched licence text (the LGPL text names the GPL) are
    # part of that text, not separate statements
    for d in match_notices(text):
        if d.lines and any(a <= d.lines[0] <= b for a, b in spans):
            continue
        dets.append(d)
    return dedupe(dets)


_RANK = {"full text": 0, "SPDX-License-Identifier": 1, "contains text": 2, "name": 3, "URL": 4}


def dedupe(dets: Iterable[Detection]) -> list[Detection]:
    best: dict[str, Detection] = {}
    for d in dets:
        key = spdx.normalise(d.expression) or d.expression
        cur = best.get(key)
        if cur is None or _RANK.get(d.method, 9) < _RANK.get(cur.method, 9):
            best[key] = d
    # a versionless CC mention next to a versioned one of the same elements adds nothing
    versioned = {k for k, d in best.items() if not d.versionless}
    out = []
    for k, d in best.items():
        if d.versionless and any(v.startswith(k + "-") for v in versioned):
            continue
        out.append(d)
    return sorted(out, key=lambda d: (d.lines or (0, 0), d.expression))
