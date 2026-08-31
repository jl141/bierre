"""Pure text helpers shared across the pipeline.

Nothing here performs I/O or depends on the rest of the package, so these
functions are safe to use from any module (and easy to unit-test in isolation).
"""

from __future__ import annotations

import html
import re

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9.+/-]{1,}")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")
_NEGATION_CUES = (
    "no ",
    "not ",
    "without ",
    "lack of ",
    "lacks ",
    "did not report ",
    "not reported ",
    "rather than ",
)


def compact_whitespace(value: object) -> str:
    """Collapse runs of whitespace and strip control characters."""
    if value is None:
        return ""
    cleaned = _CONTROL_CHARS.sub(" ", str(value))
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_markup(value: object) -> str:
    """Unescape HTML entities and drop tags (abstracts often arrive as HTML)."""
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return compact_whitespace(text)


def normalize_doi(value: object) -> str:
    """Reduce any DOI form (URL, ``doi:`` prefix, …) to the bare ``10.x/...`` id."""
    raw = compact_whitespace(value).lower()
    if not raw:
        return ""
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        raw = raw.replace(prefix, "")
    match = re.search(r"10\.\d{4,9}/[^\s\"<>]+", raw)
    if match:
        raw = match.group(0)
    return raw.strip(" .;,")


def normalize_title(value: object) -> str:
    """Lower-case, punctuation-free title used as a dedup key."""
    cleaned = compact_whitespace(strip_markup(str(value or ""))).lower()
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


def tokenize(text: str) -> list[str]:
    """Split text into lower-case word/identifier tokens."""
    return _TOKEN.findall(text.lower())


def split_sentences(text: str) -> list[str]:
    """Best-effort sentence segmentation for snippet extraction."""
    cleaned = compact_whitespace(text)
    if not cleaned:
        return []
    return [piece.strip() for piece in _SENTENCE_SPLIT.split(cleaned) if piece.strip()]


def contains(text: str, term: str) -> bool:
    """Whole-token, case-insensitive membership test.

    ``term`` may contain spaces (matched across whitespace). Word boundaries
    prevent ``"pu"`` from matching inside ``"pump"``.
    """
    term = term.lower().strip()
    if not term:
        return False
    pattern = re.escape(term).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text.lower()) is not None


def has_unnegated(text: str, term: str) -> bool:
    """True if ``term`` appears at least once without a nearby negation cue.

    This keeps sentences like *"did not report N-halamine chemistry"* from
    counting as positive evidence for ``"N-halamine"``.
    """
    lower_term = term.lower().strip()
    if not lower_term:
        return False
    for sentence in split_sentences(text) or [compact_whitespace(text)]:
        sentence_lower = sentence.lower()
        if not contains(sentence_lower, lower_term):
            continue
        offset = sentence_lower.find(lower_term)
        before = sentence_lower[:offset] if offset >= 0 else sentence_lower
        if any(cue in before for cue in _NEGATION_CUES):
            continue
        return True
    return False


def matched_terms(text: str, terms: list[str], *, unnegated: bool = False) -> list[str]:
    """Return the subset of ``terms`` present in ``text`` (order preserved)."""
    check = has_unnegated if unnegated else contains
    found: list[str] = []
    for term in terms:
        if term not in found and check(text, term):
            found.append(term)
    return found


def best_snippet(text: str, terms: list[str], *, max_words: int = 65) -> str:
    """Return the sentence with the most term hits, truncated to ``max_words``."""
    sentences = split_sentences(text)
    if not sentences:
        return ""
    best, best_score = sentences[0], -1
    for sentence in sentences:
        score = sum(1 for term in terms if contains(sentence, term))
        if score > best_score:
            best, best_score = sentence, score
    words = best.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "..."
    return best
