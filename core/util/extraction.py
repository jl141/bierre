"""Rule-based (non-LLM) evidence extraction over abstracts.

For each selected paper and each field defined by the profile, we pull the
matched terms plus the sentence(s) that mention them. This is deliberately
simple and transparent — it is a triage aid, not expert reading, and the
profile decides which fields exist.
"""

from __future__ import annotations

import re

from . import text
from ..models import EvidenceRow, RankedPaper
from ..profiles import DomainProfile, ExtractionField

_NUMERIC = re.compile(r"\d+(\.\d+)?\s*(wt%|%|ppm|mg|log|logs|cfu|cycles?|min|h|hours?)?", re.I)


def _field_value(body: str, field: ExtractionField) -> str:
    """Evidence string for one field: matched terms + supporting sentence(s)."""
    sentences = text.split_sentences(body)
    matched: list[str] = []
    evidence: list[str] = []
    for sentence in sentences:
        hits = [t for t in field.terms if text.has_unnegated(sentence, t)]
        if not hits:
            continue
        if field.require_numeric and not _NUMERIC.search(sentence):
            continue
        for hit in hits:
            if hit not in matched:
                matched.append(hit)
        evidence.append(sentence)
        if len(evidence) >= 2:
            break
    if not matched:
        return "Not reported"
    return f"Detected: {', '.join(matched[:8])}. Evidence: {' '.join(evidence)}".strip()


def extract(selected: list[RankedPaper], profile: DomainProfile) -> list[EvidenceRow]:
    """Produce one :class:`EvidenceRow` per selected paper."""
    rows: list[EvidenceRow] = []
    for item in selected:
        body = item.paper.evidence_text()
        fields = {field.name: _field_value(body, field) for field in profile.extraction_fields}
        rows.append(
            EvidenceRow(
                paper_id=item.paper.paper_id,
                title=item.paper.title,
                doi=item.paper.doi,
                fields=fields,
            )
        )
    return rows
