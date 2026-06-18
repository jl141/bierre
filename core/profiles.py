"""Domain profiles: the data that used to be hard-coded N-halamine logic.

A :class:`DomainProfile` describes everything domain-specific about a search:
which query terms to expand, which buckets papers fall into, which terms to
down-weight, and which fields to extract. Swapping the profile (``generic`` vs
``n_halamine``) changes the workflow's behaviour without touching any code.

Profiles are plain YAML in the ``profiles/`` directory; see ``generic.yaml`` for
the documented schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


@dataclass
class Concept:
    """A topic detected in the question that expands into extra query terms."""

    name: str
    triggers: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)


@dataclass
class Bucket:
    """A relevance category. The first bucket whose ``requires`` term-groups all
    match (un-negated) wins; ``fallback`` catches everything else.

    ``boost`` is added to a paper's relevance to produce its final priority, so
    on-topic buckets float to the top and off-topic ones sink.
    """

    id: str
    label: str
    boost: float = 0.0
    requires: list[str] = field(default_factory=list)
    # When true, this bucket is skipped if any off-topic term is present, so an
    # off-topic paper falls through to the fallback bucket instead of matching.
    exclude_off_topic: bool = False
    fallback: bool = False


@dataclass
class ExtractionField:
    """One column of the rule-based evidence table."""

    name: str
    terms: list[str] = field(default_factory=list)
    require_numeric: bool = False


@dataclass
class DomainProfile:
    name: str
    label: str = ""
    default_question: str = ""
    concepts: list[Concept] = field(default_factory=list)
    query_groups: dict[str, list[str]] = field(default_factory=dict)
    off_topic_terms: list[str] = field(default_factory=list)
    journal_terms: list[str] = field(default_factory=list)
    term_groups: dict[str, list[str]] = field(default_factory=dict)
    intents: dict[str, list[str]] = field(default_factory=dict)
    buckets: list[Bucket] = field(default_factory=list)
    extraction_fields: list[ExtractionField] = field(default_factory=list)

    def term_group(self, name: str) -> list[str]:
        return self.term_groups.get(name, [])

    @property
    def fallback_bucket(self) -> Bucket:
        for bucket in self.buckets:
            if bucket.fallback:
                return bucket
        # A profile with no explicit buckets ranks purely on lexical relevance.
        return Bucket(id="all", label="All", boost=0.0, fallback=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainProfile":
        # Coerce term entries to str: YAML can silently turn an unquoted token
        # like `5` (e.g. from a comma-split) into an int, which breaks matching.
        def terms(values: Any) -> list[str]:
            return [str(v) for v in (values or [])]

        return cls(
            name=data["name"],
            label=data.get("label", data["name"]),
            default_question=data.get("default_question", ""),
            concepts=[
                Concept(name=c["name"], triggers=terms(c.get("triggers")), terms=terms(c.get("terms")))
                for c in data.get("concepts", [])
            ],
            query_groups={k: terms(v) for k, v in (data.get("query_groups") or {}).items()},
            off_topic_terms=terms(data.get("off_topic_terms")),
            journal_terms=terms(data.get("journal_terms")),
            term_groups={k: terms(v) for k, v in (data.get("term_groups") or {}).items()},
            intents={k: terms(v) for k, v in (data.get("intents") or {}).items()},
            buckets=[Bucket(**b) for b in data.get("buckets", [])],
            extraction_fields=[
                ExtractionField(
                    name=f["name"],
                    terms=terms(f.get("terms")),
                    require_numeric=bool(f.get("require_numeric", False)),
                )
                for f in data.get("extraction_fields", [])
            ],
        )


def load_profile(name: str, profiles_dir: Path | None = None) -> DomainProfile:
    """Load a profile by name from the profiles directory."""
    directory = profiles_dir or PROFILES_DIR
    path = directory / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Unknown profile {name!r}: {path} not found")
    with open(path, "r", encoding="utf-8") as handle:
        return DomainProfile.from_dict(yaml.safe_load(handle) or {})


def available_profiles(profiles_dir: Path | None = None) -> list[str]:
    """List profile names discoverable in the profiles directory."""
    directory = profiles_dir or PROFILES_DIR
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.yaml"))
