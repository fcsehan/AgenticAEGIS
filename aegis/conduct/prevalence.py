"""PrevalenceResolver — resolve cross-code norm conflicts by prevalence ordering."""

from __future__ import annotations

from aegis.conduct.code_of_conduct import CodeOfConduct
from aegis.deontic.norm_frame import NormFrame


class PrevalenceResolver:
    """Resolve conflicts between norms from different codes.

    Codes with lower prevalence numbers have higher priority.
    """

    def __init__(self, codes: list[CodeOfConduct]) -> None:
        # Map code name to prevalence rank
        self._prevalence: dict[str, int] = {code.name: code.prevalence for code in codes}

    def rank_of(self, code_name: str) -> int:
        """Return the prevalence rank of *code_name*. Lower = higher priority."""
        return self._prevalence.get(code_name, 999_999)

    def higher_prevalence(self, code_a: str, code_b: str) -> str | None:
        """Return the code with higher prevalence, or None if equal."""
        rank_a = self.rank_of(code_a)
        rank_b = self.rank_of(code_b)
        if rank_a < rank_b:
            return code_a
        if rank_b < rank_a:
            return code_b
        return None

    def resolve(self, norm_a: NormFrame, norm_b: NormFrame) -> NormFrame | None:
        """Return the norm from the higher-prevalence code, or None if tied."""
        if not norm_a.code or not norm_b.code:
            return None
        winner = self.higher_prevalence(norm_a.code, norm_b.code)
        if winner == norm_a.code:
            return norm_a
        if winner == norm_b.code:
            return norm_b
        return None
