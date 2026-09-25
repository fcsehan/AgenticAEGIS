"""KnowledgeBase — the central fact store for AEGIS.

After construction and loading, the KB is frozen (D-005: immutable after startup).
All reads are lock-free.  No public assert/retract after freeze.
"""

from __future__ import annotations

from typing import Any

from aegis.engine.pattern_matcher import Term
from aegis.kb.indexing import FactIndex
from aegis.kb.microtheory import Microtheory


class KnowledgeBase:
    """Central knowledge store.

    Usage::

        kb = KnowledgeBase()
        kb.create_mt("OntologyMt")
        kb.assert_fact(("isa", "Dog", "Animal"), "OntologyMt")
        kb.freeze()
        # After freeze: query only, no mutations.
        results = kb.query(("isa", "?x", "Animal"))
    """

    def __init__(self) -> None:
        self._mts: dict[str, Microtheory] = {}
        self._index = FactIndex()
        self._frozen = False

    # ── Microtheory management ───────────────────────────────────────

    def create_mt(self, name: str, parent: str | None = None) -> Microtheory:
        """Create a new Microtheory.

        Raises:
            RuntimeError: If the KB is frozen.
            ValueError: If *parent* is specified but does not exist.
        """
        self._check_mutable()
        parent_mt = None
        if parent is not None:
            parent_mt = self._mts.get(parent)
            if parent_mt is None:
                raise ValueError(f"Parent microtheory not found: {parent!r}")
        mt = Microtheory(name=name, parent=parent_mt)
        self._mts[name] = mt
        return mt

    def get_mt(self, name: str) -> Microtheory | None:
        """Return the named Mt, or None."""
        return self._mts.get(name)

    @property
    def microtheories(self) -> list[str]:
        """Names of all microtheories."""
        return list(self._mts)

    # ── Fact management ──────────────────────────────────────────────

    def assert_fact(self, fact: tuple[Any, ...], mt_name: str) -> bool:
        """Assert *fact* into Mt *mt_name*. Returns True if new.

        Raises:
            RuntimeError: If the KB is frozen.
            KeyError: If *mt_name* does not exist.
        """
        self._check_mutable()
        mt = self._mts.get(mt_name)
        if mt is None:
            raise KeyError(f"Microtheory not found: {mt_name!r}")
        mt.assert_fact(fact)
        return self._index.assert_fact(fact, mt_name)

    def retract_fact(self, fact: tuple[Any, ...], mt_name: str) -> bool:
        """Remove *fact* from Mt *mt_name*. Returns True if removed.

        Raises:
            RuntimeError: If the KB is frozen.
        """
        self._check_mutable()
        mt = self._mts.get(mt_name)
        if mt is None:
            return False
        if fact in mt.facts:
            mt.facts.remove(fact)
            return True
        return False

    # ── Queries (safe on frozen KB) ──────────────────────────────────

    def query(self, pattern: Term) -> list[Term]:
        """Find all facts matching *pattern* via unification."""
        return self._index.query(pattern)

    def query_mt(self, pattern: Term, mt_name: str) -> list[Term]:
        """Find matching facts that were asserted in *mt_name*."""
        return self._index.query_mt(pattern, mt_name)

    def facts_in_mt(self, mt_name: str) -> list[tuple[Any, ...]]:
        """Return all facts in *mt_name*."""
        return self._index.facts_in_mt(mt_name)

    # ── Freeze (D-005) ───────────────────────────────────────────────

    def freeze(self) -> None:
        """Make the KB immutable. No further assert/retract allowed."""
        self._frozen = True

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def _check_mutable(self) -> None:
        if self._frozen:
            raise RuntimeError("KnowledgeBase is frozen — no mutations allowed (D-005)")

    # ── Stats ────────────────────────────────────────────────────────

    @property
    def fact_count(self) -> int:
        return len(self._index)

    def __repr__(self) -> str:
        state = "frozen" if self._frozen else "mutable"
        return f"KnowledgeBase({state}, mts={len(self._mts)}, facts={self.fact_count})"
