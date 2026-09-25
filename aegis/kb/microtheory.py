"""Microtheory — a named context for assertions with parent inheritance.

MELD organizes knowledge into microtheories (Mts).  Each Mt has a name
and an optional parent.  Queries walk up the parent chain, so assertions
in a parent Mt are visible to all children.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Microtheory:
    """A named assertion context.

    Attributes:
        name: The Mt name (e.g. ``"IAMissionDeonticRulesMt"``).
        parent: Optional parent Mt (queries inherit parent facts).
        facts: Assertions local to this Mt.
    """

    name: str
    parent: Microtheory | None = None
    facts: list[tuple[Any, ...]] = field(default_factory=list)

    def assert_fact(self, fact: tuple[Any, ...]) -> bool:
        """Assert *fact* into this Mt. Returns True if new (idempotent)."""
        if fact in self.facts:
            return False
        self.facts.append(fact)
        return True

    def query_local(self, predicate: str | None = None) -> list[tuple[Any, ...]]:
        """Return facts local to this Mt, optionally filtered by leading predicate."""
        if predicate is None:
            return list(self.facts)
        return [f for f in self.facts if isinstance(f, tuple) and f and f[0] == predicate]

    def query(self, predicate: str | None = None) -> list[tuple[Any, ...]]:
        """Return facts visible from this Mt (local + all ancestors).

        Walks up the parent chain, collecting matching facts.
        """
        result: list[tuple[Any, ...]] = []
        for mt in self.chain():
            result.extend(mt.query_local(predicate))
        return result

    def chain(self) -> Iterator[Microtheory]:
        """Yield this Mt followed by all ancestors (self first)."""
        current: Microtheory | None = self
        visited: set[str] = set()
        while current is not None:
            if current.name in visited:
                break  # cycle guard
            visited.add(current.name)
            yield current
            current = current.parent

    def __repr__(self) -> str:
        parent_name = self.parent.name if self.parent else None
        return f"Microtheory({self.name!r}, parent={parent_name!r}, facts={len(self.facts)})"
