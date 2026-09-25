"""Inheritance graph — build specificity ordering from genls/isa.

The inheritance graph determines which norms are more specific.
Specificity = depth from root in the genls hierarchy.
Cycle detection raises InheritanceCycleError (D-004).
"""

from __future__ import annotations

from aegis.kb.builtins import BuiltinEngine


class InheritanceGraph:
    """Inheritance graph for specificity computation.

    Built from the BuiltinEngine's transitive closures.  Provides
    specificity scores used by DDIC for conflict resolution.
    """

    def __init__(self, reasoner: BuiltinEngine) -> None:
        self._reasoner = reasoner
        self._specificity_cache: dict[str, int] = {}

    def specificity_of(self, typ: str) -> int:
        """Return the specificity (depth from root) of *typ*.

        Higher values mean more specific.  Returns 0 for root types
        or types not in the hierarchy.
        """
        if typ in self._specificity_cache:
            return self._specificity_cache[typ]

        depth = self._reasoner.depth_of(typ)
        self._specificity_cache[typ] = depth
        return depth

    def is_subtype(self, sub: str, sup: str) -> bool:
        """True if *sub* is a subtype of *sup* (via genls)."""
        return self._reasoner.is_genls(sub, sup)

    def is_instance(self, instance: str, typ: str) -> bool:
        """True if *instance* isa *typ*."""
        return self._reasoner.is_isa(instance, typ)

    def common_ancestor(self, a: str, b: str) -> str | None:
        """Find the most specific common ancestor of *a* and *b*.

        Returns None if no common ancestor exists.
        """
        ancestors_a = self._reasoner.all_genls(a) | {a}
        ancestors_b = self._reasoner.all_genls(b) | {b}
        common = ancestors_a & ancestors_b
        if not common:
            return None
        # Most specific = deepest
        return max(common, key=lambda t: self.specificity_of(t))
