"""Score and select papers for a question, guided by the domain profile.

Relevance is a hybrid of lexical similarity (BM25), semantic similarity
(TF-IDF cosine), fuzzy title matching, question-term coverage, intent coverage
and metadata quality. The profile then classifies each paper into a bucket whose
boost/penalty produces the ``final_priority`` used for ordering and selection.

The optional ranking libraries (rank-bm25, scikit-learn, rapidfuzz) degrade
gracefully: if any are missing the relevant signal falls back to a simpler
token-overlap estimate so the pipeline still runs.
"""

from __future__ import annotations

from . import text
from ..config import Settings
from ..models import Paper, RankedPaper
from .planner import analyze_question
from ..profiles import Bucket, DomainProfile

# --- individual relevance signals -------------------------------------------------


def _normalise(values: list[float]) -> list[float]:
    top = max(values) if values else 0.0
    if top <= 0:
        return [0.0 for _ in values]
    return [max(min(v / top, 1.0), 0.0) for v in values]


def _bm25(query: str, docs: list[str]) -> list[float]:
    try:
        from rank_bm25 import BM25Okapi

        bm25 = BM25Okapi([text.tokenize(d) for d in docs])
        return _normalise([float(s) for s in bm25.get_scores(text.tokenize(query))])
    except Exception:
        query_terms = set(text.tokenize(query))
        return _normalise([float(len(query_terms & set(text.tokenize(d)))) for d in docs])


def _tfidf(query: str, docs: list[str]) -> list[float]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
        matrix = vectorizer.fit_transform([query] + docs)
        scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten().tolist()
        return _normalise([float(s) for s in scores])
    except Exception:
        return [0.0 for _ in docs]


def _fuzzy_titles(query: str, papers: list[Paper]) -> list[float]:
    try:
        from rapidfuzz import fuzz

        return [
            max(
                fuzz.token_set_ratio(query, p.title) / 100.0,
                fuzz.partial_ratio(query, p.title) / 100.0,
            )
            for p in papers
        ]
    except Exception:
        return [0.0 for _ in papers]


def _coverage(doc: str, terms: list[str], max_terms: int = 10) -> float:
    useful = [t for t in terms if len(t) >= 4]
    if not useful:
        return 0.0
    hits = sum(1 for t in useful[:max_terms] if text.contains(doc, t))
    return hits / min(len(useful), max_terms)


def _intent(doc: str, profile: DomainProfile, active_concepts: list[str]) -> float:
    expected = [name for name in profile.intents if name in active_concepts]
    if not expected:
        return 0.0
    matched = sum(
        1 for name in expected if any(text.contains(doc, t) for t in profile.intents[name])
    )
    return matched / len(expected)


def _quality(paper: Paper, profile: DomainProfile) -> float:
    score = 0.0
    if paper.abstract:
        score += 0.30
    if paper.doi:
        score += 0.20
    if paper.pdf_url:
        score += 0.15
    if any(t in paper.journal.lower() for t in profile.journal_terms):
        score += 0.15
    if len(paper.sources) >= 2:
        score += 0.10
    try:
        year = int(float(str(paper.year)))
        if year >= 2022:
            score += 0.10
        elif year >= 2018:
            score += 0.05
    except (TypeError, ValueError):
        pass
    if (paper.citation_count or 0) >= 50:
        score += 0.10
    return min(score, 1.0)


# --- bucket classification --------------------------------------------------------


def _classify(paper: Paper, profile: DomainProfile) -> tuple[Bucket, dict[str, list[str]]]:
    """Return the first matching bucket and the term-groups that matched."""
    doc = paper.classification_text()
    matched = {
        name: text.matched_terms(doc, terms, unnegated=True)
        for name, terms in profile.term_groups.items()
    }
    off_topic = any(text.contains(doc, t) for t in profile.off_topic_terms)
    for bucket in profile.buckets:
        if bucket.fallback:
            continue
        if bucket.exclude_off_topic and off_topic:
            continue
        if all(matched.get(group) for group in bucket.requires):
            return bucket, matched
    return profile.fallback_bucket, matched


def _off_topic_penalty(paper: Paper, profile: DomainProfile, is_fallback: bool) -> float:
    doc = paper.classification_text()
    hits = [t for t in profile.off_topic_terms if text.contains(doc, t)]
    if not hits:
        return 0.0
    # Down-weight, don't delete: a paper with real on-topic signal (i.e. it
    # landed in a non-fallback bucket) keeps only a token penalty.
    return min(35.0, 15.0 + len(hits) * 5.0) if is_fallback else min(10.0, len(hits) * 2.0)


def _level(percent: float) -> str:
    if percent >= 75:
        return "High"
    if percent >= 55:
        return "Medium"
    if percent >= 35:
        return "Low-Medium"
    return "Low"


# --- public entry point -----------------------------------------------------------


def rank_and_select(
    papers: list[Paper],
    question: str,
    profile: DomainProfile,
    settings: Settings,
) -> list[RankedPaper]:
    """Score every paper, classify it, then mark the selected subset."""
    analysis = analyze_question(question, profile)
    query_terms = [question] + analysis.keywords[:16] + analysis.expanded_terms[:12]
    query = text.compact_whitespace(" ".join(query_terms))
    docs = [p.document_text() for p in papers]

    bm25 = _bm25(query, docs)
    tfidf = _tfidf(query, docs)
    fuzzy = _fuzzy_titles(query, papers)
    priority = {bucket.id: index for index, bucket in enumerate(profile.buckets)}

    ranked: list[RankedPaper] = []
    for i, paper in enumerate(papers):
        doc = docs[i].lower()
        phrase = _coverage(doc, analysis.keywords)
        expanded = _coverage(doc, analysis.expanded_terms)
        intent = _intent(doc, profile, analysis.concepts)
        quality = _quality(paper, profile)
        percent = round(
            min(
                bm25[i] * 28 + tfidf[i] * 24 + fuzzy[i] * 12
                + phrase * 14 + expanded * 8 + intent * 9 + quality * 5,
                100.0,
            ),
            1,
        )

        bucket, matched = _classify(paper, profile)
        penalty = _off_topic_penalty(paper, profile, bucket.fallback)
        final = round(max(min(percent + bucket.boost - penalty, 100.0), 0.0), 1)

        reasons = [
            f"lexical {bm25[i] * 100:.0f}%",
            f"semantic {tfidf[i] * 100:.0f}%",
            f"title {fuzzy[i] * 100:.0f}%",
        ]
        signal = "; ".join(f"{g}: {', '.join(m[:4])}" for g, m in matched.items() if m)
        if signal:
            reasons.append(f"matched {signal}")
        if penalty:
            reasons.append(f"off-topic penalty -{penalty:.0f}")

        ranked.append(
            RankedPaper(
                paper=paper,
                relevance=percent,
                level=_level(percent),
                reasons=reasons,
                bucket=bucket.id,
                bucket_label=bucket.label,
                final_priority=final,
                off_topic_penalty=penalty,
                matched=matched,
                snippet=text.best_snippet(paper.evidence_text(), analysis.keywords + analysis.expanded_terms),
            )
        )

    # Highest-priority bucket first, then final priority, then recency.
    ranked.sort(
        key=lambda r: (
            -priority.get(r.bucket, len(profile.buckets)),
            r.final_priority,
        ),
        reverse=True,
    )

    _apply_selection(ranked, profile, settings)
    for rank, item in enumerate(ranked, start=1):
        item.rank = rank
        item.question_relevance = _question_relevance(item)
    return ranked


def _apply_selection(ranked: list[RankedPaper], profile: DomainProfile, settings: Settings) -> None:
    sel = settings.selection
    if not sel.enabled:
        for item in ranked:
            item.selected = True
        return
    # On-topic (non-fallback) papers are always candidates; fallback-bucket
    # papers must clear the relevance floor to be worth extracting.
    candidates = [
        item
        for item in ranked
        if item.bucket != profile.fallback_bucket.id or item.relevance >= sel.min_relevance
    ]
    if not candidates:
        candidates = ranked
    for item in candidates[: max(sel.top_n, 0)]:
        item.selected = True


def _question_relevance(item: RankedPaper) -> str:
    hits = [t for terms in item.matched.values() for t in terms][:6]
    if hits:
        why = f"matches {', '.join(hits)}"
    else:
        why = "retained on lexical/semantic relevance with limited direct term overlap"
    return f"{item.level} relevance ({item.relevance:.0f}%). This paper {why}. Most relevant text: {item.snippet}"
