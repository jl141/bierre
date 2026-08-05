"""Dispatch-policy primitives shared by search-source adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..config import Settings


@dataclass
class SourceDispatchState:
    """Mutable per-run state that policy functions can share safely."""

    source_counts: dict[str, int] = field(default_factory=dict)

    def count(self, source: str) -> int:
        return self.source_counts.get(source, 0)

    def increment(self, source: str) -> None:
        self.source_counts[source] = self.count(source) + 1

    def consume_budget(self, source: str, budget: int) -> bool:
        budget = max(int(budget), 0)
        if self.count(source) >= budget:
            return False
        self.increment(source)
        return True


DispatchPredicate = Callable[[Settings, SourceDispatchState], bool]


@dataclass(frozen=True)
class SourcePolicy:
    allow_dispatch: DispatchPredicate
    force_serial: DispatchPredicate


def allow_always(settings: Settings, state: SourceDispatchState) -> bool:
    del settings, state
    return True


def never_force_serial(settings: Settings, state: SourceDispatchState) -> bool:
    del settings, state
    return False
