"""NormStatus — the result of DDIC evaluation for a single proposition.

Carries the evaluated modality, the norms that contributed to the decision,
and a human-readable justification chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aegis.deontic.modality import DeonticModality

if TYPE_CHECKING:
    from aegis.deontic.norm_frame import NormFrame


@dataclass(frozen=True, slots=True)
class NormStatus:
    """Evaluated deontic status for a proposition.

    Attributes:
        modality: The resolved modality (may be ``None`` if undetermined).
        winning_norms: The norm(s) that prevailed after conflict resolution.
        defeated_norms: Norms that were considered but defeated.
        reason: Short machine-readable reason tag (e.g. ``"specificity"``).
        justification_chain: Ordered list of reasoning steps for audit.
    """

    modality: DeonticModality | None
    winning_norms: tuple[NormFrame, ...] = ()
    defeated_norms: tuple[NormFrame, ...] = ()
    reason: str = ""
    justification_chain: tuple[str, ...] = field(default_factory=tuple)

    def is_permitted(self) -> bool:
        """True if the evaluated status is PERMITTED."""
        return self.modality == DeonticModality.PERMITTED

    def is_forbidden(self) -> bool:
        """True if the evaluated status is FORBIDDEN."""
        return self.modality == DeonticModality.FORBIDDEN

    def is_obligatory(self) -> bool:
        """True if the evaluated status is OBLIGATORY."""
        return self.modality == DeonticModality.OBLIGATORY

    def is_undetermined(self) -> bool:
        """True if evaluation could not determine a modality."""
        return self.modality is None

    def explain(self) -> str:
        """Return a human-readable explanation of the evaluation result."""
        lines: list[str] = []

        if self.modality is not None:
            lines.append(f"Status: {self.modality.value}")
        else:
            lines.append("Status: UNDETERMINED")

        if self.reason:
            lines.append(f"Reason: {self.reason}")

        if self.winning_norms:
            lines.append("Winning norms:")
            for norm in self.winning_norms:
                lines.append(
                    f"  - {norm.source}: {norm.modality.value} (specificity={norm.specificity})"
                )

        if self.defeated_norms:
            lines.append("Defeated norms:")
            for norm in self.defeated_norms:
                lines.append(
                    f"  - {norm.source}: {norm.modality.value} (specificity={norm.specificity})"
                )

        if self.justification_chain:
            lines.append("Justification chain:")
            for step in self.justification_chain:
                lines.append(f"  {step}")

        return "\n".join(lines)
