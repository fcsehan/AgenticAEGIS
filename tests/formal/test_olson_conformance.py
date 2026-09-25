"""Olson conformance tests: Theorems 6.4.1–6.4.4.

Systematic conflict-resolution tests parameterized by modality pairs and
subsumption relations. They use evaluate_legacy_module on compiled DDIC
formulas and compare the legacy implementation.
Reference: A Formal Theory of Norms, Chapter 6.4, pp. 124–149."""

from __future__ import annotations

import pytest

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.ddic_eval import DDICVerdict, evaluate_legacy_module
from aegis.engine.normframe_compile import compile_norms_to_module
from aegis.engine.inheritance import InheritanceGraph
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


# ── Fixtures ────────────────────────────────────────────────────────

OBL = DeonticModality.OBLIGATORY
FRB = DeonticModality.FORBIDDEN
PRM = DeonticModality.PERMITTED


def _kb_with_hierarchy() -> tuple[KnowledgeBase, InheritanceGraph]:
    kb = KnowledgeBase()
    mt = "TestMt"
    kb.create_mt(mt)
    # agent < seniorAgent < specialAgent (more specific = higher depth)
    kb.assert_fact(("genls", "seniorAgent", "agent"), mt)
    kb.assert_fact(("genls", "specialAgent", "seniorAgent"), mt)
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return kb, InheritanceGraph(reasoner)


def _norm(
    modality: DeonticModality,
    agent: str = "agent",
    prop: tuple[str, ...] = ("doThing",),
    code: str = "Code",
    specificity: int = 0,
    defeasible: bool = True,
    source: str = "",
) -> NormFrame:
    return NormFrame(
        code=code,
        agent_pattern=agent,
        modality=modality,
        proposition=prop,
        specificity=specificity,
        defeasible=defeasible,
        source=source or f"test:{id(object())}",
    )


def _eval_unified(
    norms: list[NormFrame],
    prop: tuple[str, ...],
    agent: str,
    kb: KnowledgeBase | None = None,
    inheritance: InheritanceGraph | None = None,
    code_prevalence: list[str] | None = None,
) -> DDICVerdict:
    """Evaluate via the unified legacy module."""
    module = compile_norms_to_module(
        norms, kb, code_prevalence=code_prevalence,
    )
    state = evaluate_legacy_module(module, prop, agent, inheritance)
    return state.verdict


def _eval_v1(
    norms: list[NormFrame],
    prop: tuple[str, ...],
    agent: str,
    inheritance: InheritanceGraph | None = None,
    code_prevalence: list[str] | None = None,
) -> DeonticModality | None:
    """Evaluate via the v1 DDICEngine."""
    if inheritance is None:
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        reasoner = BuiltinEngine(kb)
        reasoner.compute()
        inheritance = InheritanceGraph(reasoner)
    engine = DDICEngine(inheritance, code_prevalence=code_prevalence)
    status = engine.evaluate(prop, agent, norms)
    return status.modality


# ── Theorem 6.4.1: Overriding by subsumption ───────────────────────
#
# Later subsumed obligations and permissions create exceptions to prohibitions.
#
# A more-specific permission/obligation defeats a less-specific prohibition.


class TestTheorem641_OverridingBySubsumption:
    """More-specific permissions override less-specific prohibitions."""

    @pytest.mark.parametrize("winner_mod", [OBL, PRM])
    def test_more_specific_obligation_overrides_prohibition(
        self, winner_mod: DeonticModality
    ) -> None:
        kb, inh = _kb_with_hierarchy()
        # General prohibition at agent level
        general = _norm(FRB, agent="agent", specificity=0, source="gen:1")
        # More specific obligation/permission at seniorAgent level
        specific = _norm(winner_mod, agent="seniorAgent", specificity=1, source="spec:2")
        norms = [general, specific]

        # v1 engine
        v1_result = _eval_v1(norms, ("doThing",), "seniorAgent", inh)
        assert v1_result == winner_mod

        # Unified engine
        unified_result = _eval_unified(norms, ("doThing",), "seniorAgent", kb, inh)
        expected = DDICVerdict.PERMITTED  # OBL and PRM both → PERMITTED
        assert unified_result == expected

    def test_axiom_prohibition_cannot_be_overridden(self) -> None:
        """Non-defeasible prohibition wins even against defeasible permission
        at same agent level."""
        kb, inh = _kb_with_hierarchy()
        axiom = _norm(FRB, agent="agent", specificity=0, defeasible=False, source="ax:1")
        specific = _norm(PRM, agent="agent", specificity=0, source="sp:2")
        norms = [axiom, specific]

        v1_result = _eval_v1(norms, ("doThing",), "agent", inh)
        assert v1_result == FRB

        unified_result = _eval_unified(norms, ("doThing",), "agent", kb, inh)
        assert unified_result == DDICVerdict.FORBIDDEN


# ── Theorem 6.4.2: Suppression by subsumption ──────────────────────
#
# A later subsuming prohibition suppresses obligations and permissions.
#
# A more-specific prohibition defeats a less-specific permission.


class TestTheorem642_SuppressionBySubsumption:
    """More-specific prohibitions suppress less-specific permissions."""

    @pytest.mark.parametrize("loser_mod", [OBL, PRM])
    def test_more_specific_prohibition_suppresses_permission(
        self, loser_mod: DeonticModality
    ) -> None:
        kb, inh = _kb_with_hierarchy()
        general = _norm(loser_mod, agent="agent", specificity=0, source="gen:1")
        specific = _norm(FRB, agent="seniorAgent", specificity=1, source="spec:2")
        norms = [general, specific]

        v1_result = _eval_v1(norms, ("doThing",), "seniorAgent", inh)
        assert v1_result == FRB

        unified_result = _eval_unified(norms, ("doThing",), "seniorAgent", kb, inh)
        assert unified_result == DDICVerdict.FORBIDDEN

    def test_axiom_permission_cannot_be_suppressed(self) -> None:
        """Non-defeasible permission wins against defeasible prohibition
        at same agent level."""
        kb, inh = _kb_with_hierarchy()
        axiom = _norm(PRM, agent="agent", specificity=0, defeasible=False, source="ax:1")
        specific = _norm(FRB, agent="agent", specificity=0, source="sp:2")
        norms = [axiom, specific]

        v1_result = _eval_v1(norms, ("doThing",), "agent", inh)
        assert v1_result == PRM

        unified_result = _eval_unified(norms, ("doThing",), "agent", kb, inh)
        assert unified_result == DDICVerdict.PERMITTED


# ── Theorem 6.4.3: Strict subsumption defeat ───────────────────────
#
# Strictly subsumed prohibitions add exceptions regardless of input order.


class TestTheorem643_StrictSubsumptionDefeat:
    """Strictly subsumed prohibitions defeat obligations regardless of order."""

    @pytest.mark.parametrize("loser_mod", [OBL, PRM])
    def test_strictly_subsumed_prohibition_wins(
        self, loser_mod: DeonticModality
    ) -> None:
        kb, inh = _kb_with_hierarchy()
        broad_perm = _norm(loser_mod, agent="agent", specificity=0, source="broad:1")
        narrow_forbid = _norm(FRB, agent="specialAgent", specificity=2, source="narrow:2")
        norms = [broad_perm, narrow_forbid]

        v1_result = _eval_v1(norms, ("doThing",), "specialAgent", inh)
        assert v1_result == FRB

        unified_result = _eval_unified(norms, ("doThing",), "specialAgent", kb, inh)
        assert unified_result == DDICVerdict.FORBIDDEN

    @pytest.mark.parametrize("winner_mod", [OBL, PRM])
    def test_strictly_subsumed_permission_wins(
        self, winner_mod: DeonticModality
    ) -> None:
        kb, inh = _kb_with_hierarchy()
        broad_forbid = _norm(FRB, agent="agent", specificity=0, source="broad:1")
        narrow_perm = _norm(winner_mod, agent="specialAgent", specificity=2, source="narrow:2")
        norms = [broad_forbid, narrow_perm]

        v1_result = _eval_v1(norms, ("doThing",), "specialAgent", inh)
        assert v1_result == winner_mod

        unified_result = _eval_unified(norms, ("doThing",), "specialAgent", kb, inh)
        assert unified_result == DDICVerdict.PERMITTED


# ── Theorem 6.4.4: Intersecting conflicts ──────────────────────────
#
# With no subsumption, the prohibition defeats the obligation at the overlap.
#
# Equal-specificity conflicts without subsumption → UNDETERMINED.


class TestTheorem644_IntersectingConflicts:
    """Non-subsumable conflicts at the same specificity are unresolvable."""

    @pytest.mark.parametrize(
        "mod_a,mod_b",
        [
            (OBL, FRB),
            (PRM, FRB),
            (FRB, OBL),
            (FRB, PRM),
        ],
    )
    def test_same_specificity_conflict_is_undetermined(
        self, mod_a: DeonticModality, mod_b: DeonticModality
    ) -> None:
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(mod_a, agent="agent", specificity=0, code="CodeA", source="a:1")
        n2 = _norm(mod_b, agent="agent", specificity=0, code="CodeA", source="b:2")
        norms = [n1, n2]

        v1_result = _eval_v1(norms, ("doThing",), "agent", inh)
        assert v1_result is None  # UNDETERMINED

        unified_result = _eval_unified(norms, ("doThing",), "agent", kb, inh)
        assert unified_result == DDICVerdict.UNDECIDABLE

    def test_code_prevalence_resolves_intersection(self) -> None:
        """Cross-code prevalence can resolve intersecting conflicts."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(FRB, agent="agent", specificity=0, code="HighCode", source="h:1")
        n2 = _norm(PRM, agent="agent", specificity=0, code="LowCode", source="l:2")
        prevalence = ["HighCode", "LowCode"]
        norms = [n1, n2]

        v1_result = _eval_v1(norms, ("doThing",), "agent", inh, prevalence)
        assert v1_result == FRB

        unified_result = _eval_unified(
            norms, ("doThing",), "agent", kb, inh, prevalence
        )
        assert unified_result == DDICVerdict.FORBIDDEN

    def test_contradictory_axioms_are_undecidable(self) -> None:
        """Two non-defeasible axioms in conflict → UNDETERMINED."""
        kb, inh = _kb_with_hierarchy()
        a1 = _norm(OBL, agent="agent", defeasible=False, source="ax1:1")
        a2 = _norm(FRB, agent="agent", defeasible=False, source="ax2:2")
        norms = [a1, a2]

        v1_result = _eval_v1(norms, ("doThing",), "agent", inh)
        assert v1_result is None

        unified_result = _eval_unified(norms, ("doThing",), "agent", kb, inh)
        assert unified_result == DDICVerdict.UNDECIDABLE


# ── Cross-path equivalence: parametric sweep ────────────────────────


_MODALITY_PAIRS = [
    (OBL, FRB),
    (PRM, FRB),
    (FRB, OBL),
    (FRB, PRM),
]
_SPECIFICITY_PAIRS = [
    (0, 1, "n1 < n2"),
    (1, 0, "n1 > n2"),
    (0, 0, "n1 = n2"),
]
_DEFEASIBILITY_PAIRS = [
    (True, True, "both defeasible"),
    (False, True, "n1 axiom"),
    (True, False, "n2 axiom"),
]


@pytest.mark.parametrize("mod_a,mod_b", _MODALITY_PAIRS)
@pytest.mark.parametrize("spec_a,spec_b,spec_label", _SPECIFICITY_PAIRS)
@pytest.mark.parametrize("def_a,def_b,def_label", _DEFEASIBILITY_PAIRS)
class TestParametricSweep:
    """Parametric sweep: v1 DDICEngine and unified evaluate_legacy_module
    must produce equivalent verdicts for all modality × specificity ×
    defeasibility combinations."""

    def test_verdict_equivalence(
        self,
        mod_a: DeonticModality,
        mod_b: DeonticModality,
        spec_a: int,
        spec_b: int,
        spec_label: str,
        def_a: bool,
        def_b: bool,
        def_label: str,
    ) -> None:
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(mod_a, specificity=spec_a, defeasible=def_a, source="n1:1")
        n2 = _norm(mod_b, specificity=spec_b, defeasible=def_b, source="n2:2")
        norms = [n1, n2]

        v1_modality = _eval_v1(norms, ("doThing",), "agent", inh)
        unified_verdict = _eval_unified(norms, ("doThing",), "agent", kb, inh)

        # Map v1 modality to verdict for comparison
        if v1_modality is None:
            expected_verdict = DDICVerdict.UNDECIDABLE
        elif v1_modality == FRB:
            expected_verdict = DDICVerdict.FORBIDDEN
        else:
            expected_verdict = DDICVerdict.PERMITTED

        assert unified_verdict == expected_verdict, (
            f"Mismatch: {mod_a.value} vs {mod_b.value}, "
            f"spec=({spec_a},{spec_b}), def=({def_a},{def_b}): "
            f"v1={v1_modality}, unified={unified_verdict}"
        )
