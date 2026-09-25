"""ActionTypeRegistry — derived from VocabularyLoader (D-003).

Not manually defined.  The registry knows which action types exist,
what parameters they accept, and what context fields are required.

AEGIS-2903 (Epic 29) extends the registry with an Action-Substitution
disambiguation API: descriptions, synonyms, not-to-be-confused-with
pairs, and the transitive ``narrowerThan`` Subsumption graph that
Epic 32's narrowest-action selection consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.vocabulary_loader import ActionTypeSchema, VocabularyLoader


@dataclass(frozen=True, slots=True)
class ConfusablePair:
    """An asymmetric confusion warning between two action types.

    ``action_type`` is at risk of being confused with ``other`` — the
    direction matters because the prompt-time hint is rendered from the
    perspective of ``action_type``.
    """

    action_type: str
    other: str


@dataclass(frozen=True, slots=True)
class SubsumptionGraph:
    """Subsumption-Graph derived from ``narrowerThan`` MELD declarations.

    Read-only after construction. Provides O(d) transitive
    ``is_narrower_than`` lookups (d = path length) and O(k²·d)
    minimum-element selection (k = candidate set size). Acyclicity is
    enforced by the loader (AEGIS-2901, AEGIS-2902); this class trusts
    that contract.

    Used by Epic 32 (Narrowest-Action-Preference): given a set of
    PERMITTED candidate actions, select the most specific one — i.e.
    the minimum element under the ``narrowerThan`` partial order.
    """

    # node → tuple of immediately broader nodes (each direct narrowerThan edge)
    edges: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def is_narrower_than(self, a: str, b: str) -> bool:
        """True iff ``a`` is narrower than ``b``, transitively."""
        if a == b:
            return False
        seen: set[str] = set()
        stack = list(self.edges.get(a, ()))
        while stack:
            current = stack.pop()
            if current == b:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self.edges.get(current, ()))
        return False

    def minimal_elements(self, candidates: frozenset[str]) -> frozenset[str]:
        """Return the antichain of minimal elements within ``candidates``.

        ``a`` is minimal in ``S`` iff no other ``b`` in ``S`` satisfies
        ``b narrowerThan a``. Multiple incomparable minima are returned
        as a frozenset; tie-break is the caller's responsibility (Epic 32
        uses deterministic lex sort).
        """
        result: set[str] = set()
        for a in candidates:
            dominated = False
            for b in candidates:
                if a == b:
                    continue
                if self.is_narrower_than(b, a):
                    dominated = True
                    break
            if not dominated:
                result.add(a)
        return frozenset(result)


class ActionTypeRegistry:
    """Registry of known action types, derived from the KB.

    Per D-003: .meld files are the single source of truth.
    The registry is populated by VocabularyLoader, never manually.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, ActionTypeSchema] = {}
        self._subsumption: SubsumptionGraph | None = None

    @classmethod
    def from_kb(cls, kb: KnowledgeBase) -> ActionTypeRegistry:
        """Build the registry from a loaded KnowledgeBase."""
        registry = cls()
        loader = VocabularyLoader(kb)
        registry._schemas = loader.extract()
        return registry

    def is_known(self, action_type: str) -> bool:
        """True if *action_type* is a registered action type."""
        return action_type in self._schemas

    def get_schema(self, action_type: str) -> ActionTypeSchema | None:
        """Return the schema for *action_type*, or None."""
        return self._schemas.get(action_type)

    def required_context_fields(self, action_type: str) -> list[str]:
        """Return required context field names for *action_type*."""
        schema = self._schemas.get(action_type)
        if schema is None:
            return []
        return [rc.name for rc in schema.required_context]

    @property
    def action_types(self) -> list[str]:
        """All registered action type names."""
        return list(self._schemas)

    def __len__(self) -> int:
        return len(self._schemas)

    # ── Action-Substitution disambiguation API (AEGIS-2903) ──────────

    def get_description(self, action_type: str) -> str | None:
        """Return the NL description (``actionDescription`` MELD field), or None."""
        schema = self._schemas.get(action_type)
        return schema.description if schema is not None else None

    def get_synonyms(self, action_type: str) -> list[str]:
        """Return all NL synonyms declared via ``actionSynonym``."""
        schema = self._schemas.get(action_type)
        return list(schema.synonyms) if schema is not None else []

    def get_confusables(self, action_type: str) -> list[ConfusablePair]:
        """Return all ``notToBeConfusedWith`` pairs anchored at ``action_type``."""
        schema = self._schemas.get(action_type)
        if schema is None:
            return []
        return [
            ConfusablePair(action_type=action_type, other=other)
            for other in schema.confusables
        ]

    def is_narrower_than(self, a: str, b: str) -> bool:
        """True iff action ``a`` is narrower than ``b`` (transitive).

        Implementation note: derived from the MELD-declared
        ``narrowerThan`` edges. Acyclicity is enforced at load time, so
        this method always terminates.
        """
        return self.subsumption_graph().is_narrower_than(a, b)

    def subsumption_graph(self) -> SubsumptionGraph:
        """Return the cached Subsumption-Graph for Epic-32 use.

        Materialised lazily on first call from the per-schema
        ``narrower_than`` lists; subsequent calls reuse the cached
        graph. Read-only after construction.
        """
        if self._subsumption is None:
            edges = {
                name: tuple(schema.narrower_than)
                for name, schema in self._schemas.items()
                if schema.narrower_than
            }
            self._subsumption = SubsumptionGraph(edges=edges)
        return self._subsumption
