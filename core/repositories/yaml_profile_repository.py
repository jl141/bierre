"""YAML-backed ProfileRepository implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import unicodedata

import yaml

from ..profiles import DomainProfile, PROFILES_DIR
from .profile_repository import (
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileRepository,
    ProfileSummary,
    ProfileValidationError,
    ProtectedProfileError,
)

_PROFILE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PROTECTED_IDS = {"generic", "n-halamine"}
_PROFILE_FIELDS = {
    "label",
    "default_question",
    "concepts",
    "query_groups",
    "off_topic_terms",
    "journal_terms",
    "term_groups",
    "intents",
    "buckets",
    "extraction_fields",
}


def _ensure_dir(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)


def _iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat()


def _created_epoch(path: Path) -> float:
    stat = path.stat()
    if hasattr(stat, "st_birthtime"):
        return float(stat.st_birthtime)
    return float(stat.st_ctime)


def validate_profile_id(profile_id: str) -> str:
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        raise ProfileValidationError("Profile id is required.")
    if not _PROFILE_ID_RE.fullmatch(profile_id):
        raise ProfileValidationError(
            "Profile id must match ^[a-z0-9]+(?:-[a-z0-9]+)*$ (lowercase letters, digits, hyphens)."
        )
    return profile_id


def _profile_path(profile_id: str, profiles_dir: Path | None = None) -> Path:
    directory = profiles_dir or PROFILES_DIR
    validate_profile_id(profile_id)
    return directory / f"{profile_id}.yaml"


def _slugify_label(label: str) -> str:
    text = unicodedata.normalize("NFKD", label or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "profile"


def _next_available_profile_id(base_id: str, profiles_dir: Path | None = None) -> str:
    directory = profiles_dir or PROFILES_DIR
    candidate = base_id
    suffix = 2
    while (directory / f"{candidate}.yaml").exists():
        candidate = f"{base_id}-{suffix}"
        suffix += 1
    return candidate


def generate_profile_id(label: str, profiles_dir: Path | None = None) -> str:
    """Generate a safe, unique profile id from a human-readable label."""
    base_id = _slugify_label(str(label or ""))
    return _next_available_profile_id(base_id, profiles_dir)


def _profile_to_dict(profile: DomainProfile) -> dict:
    return {
        "name": profile.name,
        "label": profile.label,
        "default_question": profile.default_question,
        "concepts": [
            {"name": c.name, "triggers": list(c.triggers), "terms": list(c.terms)}
            for c in profile.concepts
        ],
        "query_groups": {k: list(v) for k, v in profile.query_groups.items()},
        "off_topic_terms": list(profile.off_topic_terms),
        "journal_terms": list(profile.journal_terms),
        "term_groups": {k: list(v) for k, v in profile.term_groups.items()},
        "intents": {k: list(v) for k, v in profile.intents.items()},
        "buckets": [
            {
                "id": b.id,
                "label": b.label,
                "boost": b.boost,
                "requires": list(b.requires),
                "exclude_off_topic": bool(b.exclude_off_topic),
                "fallback": bool(b.fallback),
            }
            for b in profile.buckets
        ],
        "extraction_fields": [
            {
                "name": f.name,
                "terms": list(f.terms),
                "require_numeric": bool(f.require_numeric),
            }
            for f in profile.extraction_fields
        ],
    }


def _normalise_profile_payload(payload: dict, profile_id: str, *, current: dict | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ProfileValidationError("Profile payload must be a JSON object.")

    unknown = sorted(k for k in payload if k not in _PROFILE_FIELDS and k != "name")
    if unknown:
        raise ProfileValidationError(f"Unknown profile fields: {', '.join(unknown)}")

    merged: dict = {}
    if current:
        merged.update(current)
    merged.update({k: v for k, v in payload.items() if k != "name"})

    label = str(merged.get("label") or "").strip()
    if not label:
        raise ProfileValidationError("Profile label is required.")

    source = {
        "name": profile_id,
        "label": label,
        "default_question": str(merged.get("default_question") or "").strip(),
        "concepts": merged.get("concepts") or [],
        "query_groups": merged.get("query_groups") or {},
        "off_topic_terms": merged.get("off_topic_terms") or [],
        "journal_terms": merged.get("journal_terms") or [],
        "term_groups": merged.get("term_groups") or {},
        "intents": merged.get("intents") or {},
        "buckets": merged.get("buckets") or [],
        "extraction_fields": merged.get("extraction_fields") or [],
    }

    try:
        profile = DomainProfile.from_dict(source)
    except (TypeError, KeyError, ValueError) as exc:
        raise ProfileValidationError(f"Invalid profile payload: {exc}") from exc
    return _profile_to_dict(profile)


def _write_profile(path: Path, profile_data: dict) -> None:
    _ensure_dir(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(profile_data, handle, sort_keys=False, allow_unicode=True)
    temp_path.replace(path)


def list_profiles(profiles_dir: Path | None = None) -> list[ProfileSummary]:
    """Return profile metadata ordered for UI dropdown display.

    Ordering policy:
    1) `generic` profile first when present.
    2) all others by creation time (newest first).
    """
    directory = profiles_dir or PROFILES_DIR
    if not directory.exists():
        return []

    records: list[tuple[float, ProfileSummary]] = []
    for path in directory.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            data = {}
        profile_id = path.stem
        label = str(data.get("label") or data.get("name") or profile_id)
        created = _created_epoch(path)
        updated = float(path.stat().st_mtime)
        records.append(
            (
                created,
                ProfileSummary(
                    profile_id=profile_id,
                    label=label,
                    created_at=_iso_utc(created),
                    updated_at=_iso_utc(updated),
                    is_builtin=profile_id in _PROTECTED_IDS,
                ),
            )
        )

    generic = [item for _created, item in records if item.profile_id == "generic"]
    others = [(created, item) for created, item in records if item.profile_id != "generic"]
    others.sort(key=lambda row: row[0], reverse=True)
    ordered_others = [item for _created, item in others]
    return generic + ordered_others


def get_profile(profile_id: str, profiles_dir: Path | None = None) -> dict:
    """Load one profile payload for editing."""
    path = _profile_path(profile_id, profiles_dir)
    if not path.exists():
        raise ProfileNotFoundError(f"Unknown profile {profile_id!r}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profile = DomainProfile.from_dict({**data, "name": path.stem})
    return _profile_to_dict(profile)


def create_profile(payload: dict, profiles_dir: Path | None = None) -> dict:
    """Create a new profile and return its metadata + payload."""
    directory = profiles_dir or PROFILES_DIR
    requested_id = str(payload.get("name") or "").strip() if isinstance(payload, dict) else ""
    profile_id = (
        validate_profile_id(requested_id)
        if requested_id
        else generate_profile_id(str(payload.get("label") or ""), directory)
    )
    path = _profile_path(profile_id, directory)
    if path.exists():
        raise ProfileConflictError(f"Profile {profile_id!r} already exists")

    profile_data = _normalise_profile_payload(payload, profile_id)
    _write_profile(path, profile_data)
    return {"id": profile_id, "profile": profile_data}


def update_profile(profile_id: str, payload: dict, profiles_dir: Path | None = None) -> dict:
    """Update an existing profile and return its metadata + payload."""
    path = _profile_path(profile_id, profiles_dir)
    if not path.exists():
        raise ProfileNotFoundError(f"Unknown profile {profile_id!r}")

    current = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profile_data = _normalise_profile_payload(payload, profile_id, current=current)
    _write_profile(path, profile_data)
    return {"id": profile_id, "profile": profile_data}


def delete_profile(profile_id: str, profiles_dir: Path | None = None) -> None:
    """Delete a profile by id (except protected built-ins)."""
    profile_id = validate_profile_id(profile_id)
    if profile_id in _PROTECTED_IDS:
        raise ProtectedProfileError(f"Profile {profile_id!r} is protected and cannot be deleted")

    path = _profile_path(profile_id, profiles_dir)
    if not path.exists():
        raise ProfileNotFoundError(f"Unknown profile {profile_id!r}")
    path.unlink()


class YamlProfileRepository(ProfileRepository):
    """YAML implementation for ProfileRepository."""

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self._profiles_dir = profiles_dir

    def list_profiles(self) -> list[ProfileSummary]:
        return list_profiles(self._profiles_dir)

    def get_profile(self, profile_id: str) -> dict:
        return get_profile(profile_id, self._profiles_dir)

    def create_profile(self, payload: dict) -> dict:
        return create_profile(payload, self._profiles_dir)

    def update_profile(self, profile_id: str, payload: dict) -> dict:
        return update_profile(profile_id, payload, self._profiles_dir)

    def delete_profile(self, profile_id: str) -> None:
        delete_profile(profile_id, self._profiles_dir)
