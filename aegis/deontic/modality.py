"""Deontic modalities — the three fundamental normative modes.

Maps MELD predicates (oughtToDo, forbiddenToDo, permittedToDo, etc.)
to the OBLIGATORY / FORBIDDEN / PERMITTED trichotomy.
"""

from __future__ import annotations

from enum import Enum


class DeonticModality(Enum):
    """The three deontic modalities."""

    OBLIGATORY = "OBLIGATORY"
    FORBIDDEN = "FORBIDDEN"
    PERMITTED = "PERMITTED"

    def negation(self) -> DeonticModality:
        """Return the deontic negation of this modality.

        OBLIGATORY ↔ FORBIDDEN (via negationPreds oughtToDo forbiddenToDo)
        PERMITTED ↔ FORBIDDEN  (via negationPreds permittedToDo forbiddenToDo)
        """
        return _NEGATION_MAP[self]

    @staticmethod
    def from_meld_predicate(predicate: str) -> DeonticModality:
        """Map a MELD deontic predicate to its modality.

        Supports all 9 predicates from the MELD grammar.

        Raises:
            ValueError: If *predicate* is not a known deontic predicate.
        """
        try:
            return _MELD_PREDICATE_MAP[predicate]
        except KeyError:
            raise ValueError(f"Unknown deontic predicate: {predicate!r}") from None


# All 9 MELD deontic predicates:
# ToDo family (arity 2): oughtToDo, forbiddenToDo, permittedToDo
# ToDo-WRT family (arity 3): oughtToDo-WRT, forbiddenToDo-WRT, permittedToDo-WRT
# ToBe family (arity 1): oughtToBe, forbiddenToBe, permittedToBe
_MELD_PREDICATE_MAP: dict[str, DeonticModality] = {
    "oughtToDo": DeonticModality.OBLIGATORY,
    "forbiddenToDo": DeonticModality.FORBIDDEN,
    "permittedToDo": DeonticModality.PERMITTED,
    "oughtToDo-WRT": DeonticModality.OBLIGATORY,
    "forbiddenToDo-WRT": DeonticModality.FORBIDDEN,
    "permittedToDo-WRT": DeonticModality.PERMITTED,
    "oughtToBe": DeonticModality.OBLIGATORY,
    "forbiddenToBe": DeonticModality.FORBIDDEN,
    "permittedToBe": DeonticModality.PERMITTED,
}

# Deontic negation pairs (from MELD negationPreds):
# (negationPreds oughtToDo forbiddenToDo) → OBLIGATORY ↔ FORBIDDEN
# (negationPreds permittedToDo forbiddenToDo) → PERMITTED ↔ FORBIDDEN
_NEGATION_MAP: dict[DeonticModality, DeonticModality] = {
    DeonticModality.OBLIGATORY: DeonticModality.FORBIDDEN,
    DeonticModality.FORBIDDEN: DeonticModality.PERMITTED,
    DeonticModality.PERMITTED: DeonticModality.FORBIDDEN,
}

# Set of all known deontic predicates for fast membership testing.
DEONTIC_PREDICATES: frozenset[str] = frozenset(_MELD_PREDICATE_MAP)
