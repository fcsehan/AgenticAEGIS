"""CWA Evaluator — Closed World Assumption for the deontic domain.

Simplified LTMS behavior per D-001 two-layer semantics:
- If the action falls within a loaded domain and no PERMITTED norm matches,
  CWA applies → FORBIDDEN with reason CWA_NO_PERMISSION.
- If no domain covers the action type → leave as UNDETERMINED (→ UNDECIDABLE).
"""

from __future__ import annotations

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_status import NormStatus


class CWAEngine:
    """Apply the Closed World Assumption to evaluation results.

    Per D-001: Within a domain, absence of permission is prohibition.
    Outside all domains, it's UNDECIDABLE.
    """

    def apply_cwa(
        self,
        status: NormStatus,
        *,
        in_domain: bool,
    ) -> NormStatus:
        """Apply CWA to an evaluation result.

        Args:
            status: The result from DDIC evaluation.
            in_domain: Whether the action type is covered by a loaded domain.

        Returns:
            Modified NormStatus with CWA applied where appropriate.
        """
        # If we already have a determined modality, CWA doesn't apply
        if not status.is_undetermined():
            return status

        # Within a domain: no permission → FORBIDDEN (CWA)
        if in_domain:
            chain = list(status.justification_chain)
            chain.append("CWA: No permission found in domain → FORBIDDEN")
            return NormStatus(
                modality=DeonticModality.FORBIDDEN,
                winning_norms=status.winning_norms,
                defeated_norms=status.defeated_norms,
                reason="cwa_no_permission",
                justification_chain=tuple(chain),
            )

        # Outside all domains: leave as UNDETERMINED (→ UNDECIDABLE at Guard level)
        return status
