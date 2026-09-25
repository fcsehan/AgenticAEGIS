"""Builtin transitive closure predicates — isa, genls, genlPreds, negationPreds.

These predicates form the backbone of the MELD ontology.  After the KB is
frozen, the transitive closures are computed and cached for fast lookup.

Depth limit: 100 (D-007).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aegis.errors import InheritanceCycleError

if TYPE_CHECKING:
    from aegis.kb.knowledge_base import KnowledgeBase

_DEPTH_LIMIT = 100


class BuiltinEngine:
    """Compute transitive closures over isa/genls/genlPreds/negationPreds.

    Usage::

        reasoner = BuiltinEngine(kb)
        reasoner.compute()  # call after kb.freeze()
        reasoner.is_isa("Dog", "Animal")
        reasoner.all_genls("Dog")
    """

    def __init__(self, kb: KnowledgeBase) -> None:
        self._kb = kb
        # Direct edges: child → set of parents
        self._isa_direct: dict[str, set[str]] = {}
        self._genls_direct: dict[str, set[str]] = {}
        self._genl_preds_direct: dict[str, set[str]] = {}
        self._negation_preds: set[tuple[str, str]] = set()

        # Transitive closures (computed by compute())
        self._isa_closure: dict[str, frozenset[str]] = {}
        self._genls_closure: dict[str, frozenset[str]] = {}
        self._genl_preds_closure: dict[str, frozenset[str]] = {}

    def compute(self) -> None:
        """Extract edges from KB and compute all transitive closures."""
        self._extract_edges()
        self._compute_closures()

    def _extract_edges(self) -> None:
        """Extract direct edges from KB facts."""
        for fact in self._kb.query(("isa", "?x", "?y")):
            if isinstance(fact, tuple) and len(fact) == 3:
                child, parent = str(fact[1]), str(fact[2])
                self._isa_direct.setdefault(child, set()).add(parent)

        for fact in self._kb.query(("genls", "?x", "?y")):
            if isinstance(fact, tuple) and len(fact) == 3:
                child, parent = str(fact[1]), str(fact[2])
                self._genls_direct.setdefault(child, set()).add(parent)

        for fact in self._kb.query(("genlPreds", "?x", "?y")):
            if isinstance(fact, tuple) and len(fact) == 3:
                child, parent = str(fact[1]), str(fact[2])
                self._genl_preds_direct.setdefault(child, set()).add(parent)

        for fact in self._kb.query(("negationPreds", "?x", "?y")):
            if isinstance(fact, tuple) and len(fact) == 3:
                a, b = str(fact[1]), str(fact[2])
                self._negation_preds.add((a, b))
                self._negation_preds.add((b, a))

    def _compute_closures(self) -> None:
        """Compute transitive closures with cycle detection."""
        for node in self._isa_direct:
            self._isa_closure[node] = self._transitive(node, self._isa_direct, "isa")
        # genls is independently transitive
        for node in self._genls_direct:
            self._genls_closure[node] = self._transitive(node, self._genls_direct, "genls")
        # isa uses genls: if X isa Y and Y genls Z, then X isa Z
        # Extend isa closure with genls of each type
        for node, types in list(self._isa_closure.items()):
            extended: set[str] = set(types)
            for t in types:
                extended.update(self.all_genls(t))
            self._isa_closure[node] = frozenset(extended)

        for node in self._genl_preds_direct:
            self._genl_preds_closure[node] = self._transitive(
                node, self._genl_preds_direct, "genlPreds"
            )

    def _transitive(
        self,
        start: str,
        edges: dict[str, set[str]],
        predicate: str,
    ) -> frozenset[str]:
        """BFS transitive closure with cycle detection and depth limit."""
        visited: set[str] = set()
        queue: list[str] = [start]
        depth = 0

        while queue and depth < _DEPTH_LIMIT:
            next_queue: list[str] = []
            for node in queue:
                for parent in edges.get(node, ()):
                    if parent == start:
                        raise InheritanceCycleError(
                            f"Cycle detected in {predicate}: {start} → ... → {start}"
                        )
                    if parent not in visited:
                        visited.add(parent)
                        next_queue.append(parent)
            queue = next_queue
            depth += 1

        return frozenset(visited)

    # ── Public query API ─────────────────────────────────────────────

    def is_isa(self, instance: str, typ: str) -> bool:
        """True if *instance* isa *typ* (transitively)."""
        if instance == typ:
            return True
        return typ in self._isa_closure.get(instance, frozenset())

    def all_isa(self, instance: str) -> frozenset[str]:
        """All types *instance* is an instance of (transitively)."""
        return self._isa_closure.get(instance, frozenset())

    def is_genls(self, sub: str, sup: str) -> bool:
        """True if *sub* genls *sup* (transitively)."""
        if sub == sup:
            return True
        return sup in self._genls_closure.get(sub, frozenset())

    def all_genls(self, typ: str) -> frozenset[str]:
        """All supertypes of *typ* (transitively via genls)."""
        return self._genls_closure.get(typ, frozenset())

    def is_genl_pred(self, sub: str, sup: str) -> bool:
        """True if *sub* genlPreds *sup* (transitively)."""
        if sub == sup:
            return True
        return sup in self._genl_preds_closure.get(sub, frozenset())

    def are_negation_preds(self, a: str, b: str) -> bool:
        """True if *a* and *b* are negationPreds of each other."""
        return (a, b) in self._negation_preds

    def depth_of(self, typ: str) -> int:
        """Depth from root in genls hierarchy (0 if root or not in hierarchy)."""
        closure = self._genls_closure.get(typ, frozenset())
        return len(closure)
