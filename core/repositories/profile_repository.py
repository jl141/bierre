"""Repository contract + transport-agnostic profile domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Any


@dataclass
class Concept:
    """A topic detected in the question that expands into extra query terms."""

    name: str
    triggers: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)


@dataclass
class Bucket:
    """A relevance category. The first non-fallback matching bucket wins."""

    id: str
    label: str
    boost: float = 0.0
    requires: list[str] = field(default_factory=list)
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
        return Bucket(id="all", label="All", boost=0.0, fallback=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainProfile":
        # YAML may parse bare values (like 5) as ints; coerce terms to strings.
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

class ProfileStoreError(Exception):
    """Base error for profile storage operations."""


class ProfileValidationError(ProfileStoreError):
    """Payload or id does not satisfy schema/safety requirements."""


class ProfileNotFoundError(ProfileStoreError):
    """Requested profile does not exist."""


class ProfileConflictError(ProfileStoreError):
    """Create operation conflicts with an existing profile id."""


class ProtectedProfileError(ProfileStoreError):
    """Operation targets a protected built-in profile."""


@dataclass(frozen=True)
class ProfileSummary:
    profile_id: str
    label: str
    created_at: str
    updated_at: str
    is_builtin: bool

    def to_dict(self) -> dict:
        return {
            "id": self.profile_id,
            "label": self.label,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_builtin": self.is_builtin,
        }


class ProfileRepository(ABC):
    """Transport-agnostic profile persistence contract."""

    @abstractmethod
    def list_profiles(self) -> list[ProfileSummary]:
        raise NotImplementedError

    @abstractmethod
    def get_profile(self, profile_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def create_profile(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def update_profile(self, profile_id: str, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def delete_profile(self, profile_id: str) -> None:
        raise NotImplementedError
