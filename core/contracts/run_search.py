"""Canonical request/response contract for run/search operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from ..models import RunResult

CONTRACT_VERSION = "v1"


@dataclass
class RunSearchRequest:
    """Adapter-facing request DTO for one run/search operation."""

    contract_version: str = CONTRACT_VERSION
    question: str = ""
    profile_id: str = ""
    offline: bool = False
    settings_overrides: dict[str, Any] = field(default_factory=dict)
    requested_outputs: list[str] = field(default_factory=list)
    request_id: str = ""

    def __post_init__(self) -> None:
        self.contract_version = str(self.contract_version or "").strip() or CONTRACT_VERSION
        self.question = str(self.question or "").strip()
        self.profile_id = str(self.profile_id or "").strip()
        self.request_id = str(self.request_id or "").strip()

        if self.contract_version != CONTRACT_VERSION:
            raise ValueError(f"Unsupported contract_version {self.contract_version!r}")
        if not self.question:
            raise ValueError("question is required")
        if not isinstance(self.settings_overrides, dict):
            raise ValueError("settings_overrides must be an object")
        if not isinstance(self.requested_outputs, list) or any(
            not isinstance(item, str) or not item.strip() for item in self.requested_outputs
        ):
            raise ValueError("requested_outputs must be a list of non-empty strings")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunSearchRequest":
        if not isinstance(payload, dict):
            raise ValueError("RunSearchRequest payload must be an object")
        return cls(
            contract_version=payload.get("contract_version", CONTRACT_VERSION),
            question=payload.get("question", ""),
            profile_id=payload.get("profile_id", ""),
            offline=bool(payload.get("offline", False)),
            settings_overrides=dict(payload.get("settings_overrides") or {}),
            requested_outputs=list(payload.get("requested_outputs") or []),
            request_id=payload.get("request_id", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "question": self.question,
            "profile_id": self.profile_id,
            "offline": self.offline,
            "settings_overrides": dict(self.settings_overrides),
            "requested_outputs": list(self.requested_outputs),
            "request_id": self.request_id,
        }


@dataclass
class RunSearchResponse:
    """Canonical response DTO shared by CLI, webapp, and API."""

    contract_version: str
    request_id: str
    run_id: str
    timestamp: str
    mode: str
    profile_id: str
    question: str
    queries: list[str] = field(default_factory=list)
    apis_used: list[str] = field(default_factory=list)
    scoring_summary: dict[str, Any] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    papers: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.contract_version = str(self.contract_version or "").strip()
        self.request_id = str(self.request_id or "").strip()
        self.run_id = str(self.run_id or "").strip()
        self.timestamp = str(self.timestamp or "").strip()
        self.mode = str(self.mode or "").strip()
        self.profile_id = str(self.profile_id or "").strip()
        self.question = str(self.question or "").strip()

        if self.contract_version != CONTRACT_VERSION:
            raise ValueError(f"Unsupported contract_version {self.contract_version!r}")
        if not self.request_id:
            raise ValueError("request_id is required")
        if not self.run_id:
            raise ValueError("run_id is required")
        if not self.timestamp:
            raise ValueError("timestamp is required")
        if self.mode not in {"offline", "online"}:
            raise ValueError("mode must be 'offline' or 'online'")
        if not self.profile_id:
            raise ValueError("profile_id is required")
        if not self.question:
            raise ValueError("question is required")

        if not isinstance(self.scoring_summary, dict):
            raise ValueError("scoring_summary must be an object")
        required_summary = {
            "strategy",
            "selection_enabled",
            "selection_top_n",
            "selection_min_relevance",
        }
        missing_summary = [key for key in required_summary if key not in self.scoring_summary]
        if missing_summary:
            raise ValueError(f"scoring_summary missing keys: {', '.join(missing_summary)}")

        if not isinstance(self.counts, dict):
            raise ValueError("counts must be an object")
        if "found" not in self.counts or "selected" not in self.counts:
            raise ValueError("counts must include found and selected")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "profile_id": self.profile_id,
            "question": self.question,
            "queries": list(self.queries),
            "apis_used": list(self.apis_used),
            "scoring_summary": dict(self.scoring_summary),
            "counts": dict(self.counts),
            "papers": list(self.papers),
            "evidence": list(self.evidence),
            "errors": list(self.errors),
        }


def map_run_result_to_response(
    result: RunResult,
    *,
    request_id: str,
    settings: Settings,
    contract_version: str = CONTRACT_VERSION,
) -> RunSearchResponse:
    """Map internal RunResult to the stable external contract response."""

    selection = settings.selection
    return RunSearchResponse(
        contract_version=contract_version,
        request_id=request_id,
        run_id=result.run_id,
        timestamp=result.timestamp,
        mode=result.mode,
        profile_id=result.profile,
        question=result.question,
        queries=list(result.queries),
        apis_used=list(result.apis_used),
        scoring_summary={
            # Strategy is fixed for v1 even if internals evolve, keeping the
            # contract stable for clients and tests.
            "strategy": "hybrid",
            "selection_enabled": bool(selection.enabled),
            "selection_top_n": int(selection.top_n),
            "selection_min_relevance": float(selection.min_relevance),
        },
        counts={
            "found": len(result.ranked),
            "selected": len(result.selected),
        },
        papers=[item.to_dict() for item in result.ranked],
        evidence=[row.to_dict() for row in result.evidence],
        errors=list(result.errors),
    )
