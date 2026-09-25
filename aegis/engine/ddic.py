"""DDIC Engine — Defeasible Deontic Inheritance Calculus.

The heartpiece of AEGIS.  Implements Olson's DDIC algorithm:
  1. Collect applicable norms for the proposition + agent + codes
  2. Moral axioms (non-defeasible) win immediately
  3. Specificity ordering resolves remaining conflicts
  4. Preemption: more-specific norms defeat less-specific ones
  5. Cross-code prevalence: code ordering breaks remaining ties
  6. Unresolvable conflicts → UNDETERMINED

Reference: Olson, "Defeasible Deontic Inheritance Calculus" (AAAI 2023)
"""

from __future__ import annotations

from typing import Any

from aegis.deontic.conflicts import detect_conflicts
from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.deontic.norm_status import NormStatus
from aegis.engine.inheritance import InheritanceGraph
from aegis.engine.pattern_matcher import FAIL, unify
from aegis.errors import EvaluationError

# AEGIS-1901: Documented safety limit for applicable norms.
# O(n²) preemption with n=10_000 is bounded and terminates.
MAX_APPLICABLE_NORMS: int = 10_000


class DDICEngine:
    """Evaluate deontic status using the DDIC algorithm.

    Usage::

        engine = DDICEngine(inheritance_graph, code_prevalence=["CodeA", "CodeB"])
        status = engine.evaluate(
            proposition=("shareIntelligence", "classified"),
            agent="intelligenceAgent",
            norms=collected_norms,
        )
    """

    def __init__(
        self,
        inheritance: InheritanceGraph,
        code_prevalence: list[str] | None = None,
    ) -> None:
        self._inheritance = inheritance
        # Code prevalence: earlier in list = higher prevalence
        self._code_prevalence = code_prevalence or []

    def evaluate(
        self,
        proposition: tuple[Any, ...],
        agent: str,
        norms: list[NormFrame],
        context: dict[str, Any] | None = None,
    ) -> NormStatus:
        """Evaluate the deontic status of *proposition* for *agent*.

        Algorithm per Olson's DDIC:
        1. Filter norms applicable to this agent
        2. Non-defeasible norms (moral axioms) win immediately
        3. Sort remaining by specificity (higher = more specific)
        4. Apply preemption: more-specific defeats less-specific
        5. Cross-code prevalence breaks remaining ties
        6. If still conflicted → UNDETERMINED
        """
        chain: list[str] = []

        # Step 1: Filter applicable norms (agent match + proposition match)
        applicable = [
            n for n in norms if n.matches_agent(agent) and self._proposition_matches(n, proposition)
        ]
        chain.append(f"Applicable norms for agent={agent!r}: {len(applicable)}")

        # AEGIS-1901: Termination guard
        if len(applicable) > MAX_APPLICABLE_NORMS:
            raise EvaluationError(
                f"Norm count ({len(applicable)}) exceeds safety limit "
                f"({MAX_APPLICABLE_NORMS})"
            )

        if not applicable:
            return NormStatus(
                modality=None,
                reason="no_applicable_norms",
                justification_chain=tuple(chain),
            )

        # Step 2: Moral axioms (non-defeasible) — they win absolutely (I4)
        axioms = [n for n in applicable if not n.defeasible]
        defeasible = [n for n in applicable if n.defeasible]

        if axioms:
            chain.append(f"Moral axioms found: {len(axioms)}")
            # Check for contradictory axioms
            axiom_conflicts = detect_conflicts(axioms)
            if axiom_conflicts:
                chain.append("Contradictory moral axioms — UNDETERMINED")
                return NormStatus(
                    modality=None,
                    winning_norms=tuple(axioms),
                    reason="contradictory_axioms",
                    justification_chain=tuple(chain),
                )
            # All axioms agree — use their modality
            modality = axioms[0].modality
            chain.append(f"Moral axiom prevails: {modality.value}")
            return NormStatus(
                modality=modality,
                winning_norms=tuple(axioms),
                defeated_norms=tuple(defeasible),
                reason="moral_axiom",
                justification_chain=tuple(chain),
            )

        # Step 3: Sort by specificity (deterministic sort key)
        applicable_sorted = sorted(
            defeasible,
            key=lambda n: self._sort_key(n),
            reverse=True,
        )
        chain.append(f"Sorted {len(applicable_sorted)} defeasible norms by specificity")

        # Step 4: Preemption — more specific norms defeat less specific ones
        surviving, defeated = self._apply_preemption(applicable_sorted)
        chain.append(f"After preemption: {len(surviving)} surviving, {len(defeated)} defeated")

        if not surviving:
            return NormStatus(
                modality=None,
                defeated_norms=tuple(defeated),
                reason="all_defeated",
                justification_chain=tuple(chain),
            )

        # Check if surviving norms agree
        modalities = {n.modality for n in surviving}
        if len(modalities) == 1:
            modality = modalities.pop()
            chain.append(f"Unanimous surviving norms: {modality.value}")
            return NormStatus(
                modality=modality,
                winning_norms=tuple(surviving),
                defeated_norms=tuple(defeated),
                reason="specificity",
                justification_chain=tuple(chain),
            )

        # Step 5: Cross-code prevalence
        chain.append("Conflicting surviving norms — trying cross-code prevalence")
        resolved = self._resolve_by_prevalence(surviving)
        if resolved is not None:
            winner_modality = resolved[0].modality
            losers = [n for n in surviving if n.modality != winner_modality]
            chain.append(f"Cross-code prevalence resolves to: {winner_modality.value}")
            return NormStatus(
                modality=winner_modality,
                winning_norms=tuple(resolved),
                defeated_norms=tuple(defeated + losers),
                reason="cross_code_prevalence",
                justification_chain=tuple(chain),
            )

        # Step 6: Unresolvable conflict
        chain.append("Unresolvable conflict — UNDETERMINED")
        return NormStatus(
            modality=None,
            winning_norms=tuple(surviving),
            defeated_norms=tuple(defeated),
            reason="unresolved_conflict",
            justification_chain=tuple(chain),
        )

    @staticmethod
    def _proposition_matches(norm: NormFrame, proposition: tuple[Any, ...]) -> bool:
        """Check if a norm's proposition pattern matches the evaluated proposition.

        Uses unification: the norm proposition is treated as a pattern that
        must unify with the action proposition.  A norm with proposition
        ("shareIntelligence", "secret") does NOT match ("shareIntelligence", "unclassified").
        """
        result = unify(norm.proposition, proposition)
        if result is not FAIL:
            return True
        # Also try matching if proposition is a prefix/superset
        # (e.g. norm=("shareIntelligence",) matches proposition=("shareIntelligence", ...))
        if len(norm.proposition) <= len(proposition):
            result = unify(norm.proposition, proposition[: len(norm.proposition)])
            return result is not FAIL
        return False

    def _sort_key(self, norm: NormFrame) -> tuple[int, int, str, str]:
        """Deterministic sort key for norms.

        Higher is better:
        1. Specificity (higher = more specific)
        2. Code prevalence position (earlier = higher priority)
        3. Code name (alphabetical tie-break)
        4. Modality value (final tie-break for determinism)
        """
        code_rank = 0
        if norm.code in self._code_prevalence:
            # Invert so earlier codes get higher rank
            code_rank = len(self._code_prevalence) - self._code_prevalence.index(norm.code)
        return (norm.specificity, code_rank, norm.code, norm.modality.value)

    def _apply_preemption(self, norms: list[NormFrame]) -> tuple[list[NormFrame], list[NormFrame]]:
        """Apply preemption: more specific norms defeat less specific ones.

        For each conflicting pair, the more specific norm survives.
        Norms at the same specificity level both survive (they go to step 5).
        """
        defeated: set[int] = set()  # indices of defeated norms

        for i, a in enumerate(norms):
            if i in defeated:
                continue
            for j, b in enumerate(norms):
                if j <= i or j in defeated:
                    continue
                if not a.conflicts_with(b):
                    continue
                # More specific wins
                if a.specificity > b.specificity:
                    defeated.add(j)
                elif b.specificity > a.specificity:
                    defeated.add(i)
                    break  # a is defeated, no point checking further

        surviving = [n for i, n in enumerate(norms) if i not in defeated]
        defeated_norms = [n for i, n in enumerate(norms) if i in defeated]
        return surviving, defeated_norms

    def _resolve_by_prevalence(self, norms: list[NormFrame]) -> list[NormFrame] | None:
        """Try to resolve conflict via cross-code prevalence ordering.

        Returns the winning norms if one code has strictly higher prevalence,
        or None if no resolution is possible.
        """
        if not self._code_prevalence:
            return None

        # Group by modality
        by_modality: dict[DeonticModality, list[NormFrame]] = {}
        for n in norms:
            by_modality.setdefault(n.modality, []).append(n)

        if len(by_modality) < 2:
            return None  # no conflict

        # Find the modality whose norms have the highest-prevalence code
        best_modality: DeonticModality | None = None
        best_rank = -1

        for modality, mod_norms in by_modality.items():
            for n in mod_norms:
                if n.code in self._code_prevalence:
                    rank = len(self._code_prevalence) - self._code_prevalence.index(n.code)
                    if rank > best_rank:
                        best_rank = rank
                        best_modality = modality

        if best_modality is None:
            return None

        # Check that only one modality has the best code
        for modality, mod_norms in by_modality.items():
            if modality == best_modality:
                continue
            for n in mod_norms:
                if n.code in self._code_prevalence:
                    rank = len(self._code_prevalence) - self._code_prevalence.index(n.code)
                    if rank >= best_rank:
                        return None  # tie — can't resolve

        return by_modality[best_modality]
