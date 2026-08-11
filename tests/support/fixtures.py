"""Access to the shared contract fixtures in `tests/fixtures/`.

The same module sits at `tests/support/fixtures.py` in the sibling repo, because
the fixtures it reads are byte-identical in both. `fixture_bytes` returns the
stored bytes rather than a re-serialised object, so a test can assert on the
exact payload the other service sends.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
MANIFEST_PATH = FIXTURES_DIR / "MANIFEST.sha256"


def fixture_bytes(name: str) -> bytes:
    """Return the fixture named `name` (without the `.json` suffix) as stored."""
    return (FIXTURES_DIR / f"{name}.json").read_bytes()


def load_fixture(name: str) -> Any:
    return json.loads(fixture_bytes(name))


def fixture_names() -> list[str]:
    return sorted(path.name for path in FIXTURES_DIR.glob("*.json"))


def manifest() -> dict[str, str]:
    """Parse `MANIFEST.sha256` into `{file name: recorded sha256}`.

    The file is `shasum -a 256` output — digest, two spaces, file name — so it
    stays regenerable with one command and readable in a diff.
    """
    entries: dict[str, str] = {}
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        digest, _, filename = line.partition("  ")
        if digest and filename:
            entries[filename.strip()] = digest.strip()
    return entries


def digest_of(filename: str) -> str:
    return hashlib.sha256((FIXTURES_DIR / filename).read_bytes()).hexdigest()
