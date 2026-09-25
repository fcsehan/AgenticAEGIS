"""Conflict detection between deontic norms.

Implements AEGIS-105: detect and classify conflicts between NormFrames.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aegis.deontic.norm_frame import NormFrame


class ConflictType(Enum):
    """Classification of norm conflicts per Olson's DDIC."""

    PERMISSIVE_INHERITANCE = "PERMISSIVE_INHERITANCE"
    """PERMITTED vs. FORBIDDEN between norms at different specificity levels."""

    PREEMPTION = "PREEMPTION"
    """A more specific norm overrides a less specific one."""

    HIERARCHICAL = "HIERARCHICAL"
    """Conflict between norms from different codes with prevalence ordering."""


@dataclass(frozen=True, slots=True)
class Conflict:
    """A detected conflict between two norms.

    Attributes:
        norm_a: First norm in the conflict pair.
        norm_b: Second norm in the conflict pair.
        conflict_type: Classification of the conflict.
    """

    norm_a: NormFrame
    norm_b: NormFrame
    conflict_type: ConflictType


def detect_conflicts(norms: list[NormFrame]) -> list[Conflict]:
    """Find all pairwise conflicts among *norms*.

    Only norms that actually oppose each other (via ``conflicts_with``)
    are reported.  The conflict type is classified as:

    - PREEMPTION if one norm is strictly more specific than the other
    - HIERARCHICAL if the norms come from different codes
    - PERMISSIVE_INHERITANCE otherwise (same code, same specificity)

    Returns a list of ``Conflict`` objects, one per conflicting pair.
    """
    conflicts: list[Conflict] = []

    for i, a in enumerate(norms):
        for b in norms[i + 1 :]:
            if not a.conflicts_with(b):
                continue

            conflict_type = _classify(a, b)
            conflicts.append(Conflict(norm_a=a, norm_b=b, conflict_type=conflict_type))

    return conflicts


def _classify(a: NormFrame, b: NormFrame) -> ConflictType:
    """Classify the conflict between two opposing norms."""
    # Different codes → hierarchical (cross-code prevalence)
    if a.code != b.code and a.code and b.code:
        return ConflictType.HIERARCHICAL

    # Different specificity → preemption (more specific wins)
    if a.specificity != b.specificity:
        return ConflictType.PREEMPTION

    # Same code, same specificity, opposing modalities
    return ConflictType.PERMISSIVE_INHERITANCE
