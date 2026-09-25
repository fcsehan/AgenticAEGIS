"""FactIndex — DBClassTable with Microtheory awareness.

Wraps the engine's DBClassTable to provide Mt-scoped fact storage
and efficient predicate-based lookup.
"""

from __future__ import annotations

from typing import Any

from aegis.engine.dbclass import DBClassTable
from aegis.engine.pattern_matcher import Term


class FactIndex:
    """Indexed fact storage with Microtheory tracking.

    Each fact is tagged with the Mt it was asserted in, and the underlying
    DBClassTable provides O(1) lookup by leading symbol.
    """

    def __init__(self) -> None:
        self._table = DBClassTable()
        self._mt_facts: dict[str, list[tuple[Any, ...]]] = {}

    def assert_fact(self, fact: tuple[Any, ...], mt_name: str) -> bool:
        """Assert *fact* under microtheory *mt_name*. Returns True if new."""
        is_new = self._table.insert(fact)
        if is_new:
            self._mt_facts.setdefault(mt_name, []).append(fact)
        return is_new

    def query(self, pattern: Term) -> list[Term]:
        """Find all facts matching *pattern* via unification (across all Mts)."""
        return self._table.fetch(pattern)

    def query_mt(self, pattern: Term, mt_name: str) -> list[Term]:
        """Find facts matching *pattern* that were asserted in *mt_name*."""
        from aegis.engine.pattern_matcher import FAIL, sublis, unify

        mt_facts = self._mt_facts.get(mt_name, [])
        results: list[Term] = []
        for candidate in mt_facts:
            bindings = unify(pattern, candidate)
            if bindings is not FAIL:
                results.append(sublis(bindings, pattern))  # type: ignore[arg-type]
        return results

    def facts_in_mt(self, mt_name: str) -> list[tuple[Any, ...]]:
        """Return all facts asserted in *mt_name*."""
        return list(self._mt_facts.get(mt_name, []))

    def all_facts(self) -> list[tuple[Any, ...]]:
        """Return all facts across all Mts."""
        return self._table.all_facts()

    def __len__(self) -> int:
        return len(self._table)

    def __contains__(self, fact: tuple[Any, ...]) -> bool:
        return fact in self._table
