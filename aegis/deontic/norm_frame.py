"""NormFrame — the atomic unit of deontic information.

A NormFrame represents a single deontic assertion extracted from a .meld file:
  (code, agent_pattern, modality, proposition, specificity, defeasible, source)

NormFrames are frozen (immutable, hashable) so they can live in sets and
be shared safely across threads per D-005.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aegis.deontic.modality import DeonticModality


@dataclass(frozen=True, slots=True)
class NormFrame:
    """A single deontic assertion.

    Attributes:
        code: The CodeOfConduct this norm belongs to (e.g. ``"IAMissionCode"``).
              Empty string for code-independent norms (ToDo/ToBe family).
        agent_pattern: Pattern describing which agents this norm applies to
                       (e.g. ``"intelligenceAgent"`` or ``"*"`` for any).
        modality: The deontic modality (OBLIGATORY / FORBIDDEN / PERMITTED).
        proposition: The proposition (action/state) this norm governs.
                     Stored as a tuple for hashability and pattern matching.
        specificity: Depth in the inheritance hierarchy. Higher = more specific.
                     Used by DDIC for conflict resolution.
        defeasible: Whether this norm can be overridden by more specific norms.
                    Moral axioms have ``defeasible=False`` (I4).
        source: Provenance string (e.g. ``"IAMissionDeonticRulesMt.meld:42"``).
    """

    code: str
    agent_pattern: str
    modality: DeonticModality
    proposition: tuple[Any, ...]
    specificity: int = 0
    defeasible: bool = True
    source: str = ""

    def matches_agent(self, agent: str) -> bool:
        """Check whether this norm applies to *agent*.

        The wildcard ``"*"`` matches any agent.  Otherwise, exact string match.
        Inheritance-aware matching (isa/genls) is done by the DDIC engine,
        not here — this is the fast pre-filter.
        """
        return self.agent_pattern == "*" or self.agent_pattern == agent

    def is_more_specific_than(self, other: NormFrame) -> bool:
        """Return True if this norm is strictly more specific than *other*.

        Specificity is determined by depth in the inheritance hierarchy.
        """
        return self.specificity > other.specificity

    def conflicts_with(self, other: NormFrame) -> bool:
        """Return True if this norm and *other* have opposing modalities
        for the same proposition scope.

        Two norms conflict when:
        - They govern the same proposition (or overlapping propositions)
        - One is FORBIDDEN/OBLIGATORY and the other is PERMITTED, or
          one is OBLIGATORY and the other is FORBIDDEN.
        """
        if self.modality == other.modality:
            return False
        # OBLIGATORY vs FORBIDDEN is always a conflict
        if {self.modality, other.modality} == {
            DeonticModality.OBLIGATORY,
            DeonticModality.FORBIDDEN,
        }:
            return True
        # PERMITTED vs FORBIDDEN is a conflict
        # OBLIGATORY vs PERMITTED is not (obligatory implies permitted)
        return {self.modality, other.modality} == {
            DeonticModality.PERMITTED,
            DeonticModality.FORBIDDEN,
        }
