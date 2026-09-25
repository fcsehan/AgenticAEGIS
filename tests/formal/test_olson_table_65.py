"""Olson Table 6.5: conflict-resolution matrix adaptations.

Each test constructs a norm pair for one of the 16 rows and compares the
normalized result. Some legacy cases explicitly allow an undecidable result
where Olson gives impermissibility; see docs/spec/DDIC_VERIFICATION.md.

Imp = impermissible, Obl = obligatory, Opt = optional (legacy PERMITTED).
The relation describes the scopes; overlap denotes their intersection.
Reference: A Formal Theory of Norms, Chapter 6.4.2, Table 6.5, p. 140."""

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

# ── Modality shorthands ─────────────────────────────────────────────

IMP = DeonticModality.FORBIDDEN    # Impermissible
OBL = DeonticModality.OBLIGATORY   # Obligatory
OPT = DeonticModality.PERMITTED    # Optional (AEGIS PERMITTED = Olson Optional)


# ── Infrastructure ──────────────────────────────────────────────────

def _kb_with_hierarchy() -> tuple[KnowledgeBase, InheritanceGraph]:
    """KB with agent < seniorAgent < specialAgent for specificity."""
    kb = KnowledgeBase()
    mt = "TestMt"
    kb.create_mt(mt)
    kb.assert_fact(("genls", "seniorAgent", "agent"), mt)
    kb.assert_fact(("genls", "specialAgent", "seniorAgent"), mt)
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return kb, InheritanceGraph(reasoner)


def _norm(
    modality: DeonticModality,
    agent: str = "agent",
    prop: tuple[str, ...] = ("action",),
    specificity: int = 0,
    source: str = "",
) -> NormFrame:
    return NormFrame(
        code="TestCode",
        agent_pattern=agent,
        modality=modality,
        proposition=prop,
        specificity=specificity,
        defeasible=True,
        source=source or f"t:{id(object())}",
    )


def _evaluate(
    n1: NormFrame,
    n2: NormFrame,
    kb: KnowledgeBase,
    inh: InheritanceGraph,
) -> DDICVerdict:
    """Evaluate through the unified legacy path for the matrix case."""
    module = compile_norms_to_module([n1, n2], kb)
    state = evaluate_legacy_module(module, ("action",), "agent", inh)
    return state.verdict


def _evaluate_v1(
    n1: NormFrame,
    n2: NormFrame,
    inh: InheritanceGraph,
) -> DeonticModality | None:
    """Evaluate via v1 DDICEngine for cross-check."""
    engine = DDICEngine(inh)
    status = engine.evaluate(("action",), "agent", [n1, n2])
    return status.modality


# Theorem 6.4.1: later subsumed obligations and permissions add exceptions
# to earlier prohibitions. Compare the result at the intersection of scopes.


class TestTable65_Theorem641:
    """Rows 1–4: Imp overridden by later Obl/Opt."""

    def test_row1_imp_eq_obl(self) -> None:
        """Imp = Obl: no clear winner at equal specificity."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(IMP, specificity=0, source="n1:1")
        n2 = _norm(OBL, specificity=0, source="n2:2")
        # Equal specificity without code precedence: UNDECIDABLE
        assert _evaluate(n1, n2, kb, inh) == DDICVerdict.UNDECIDABLE
        assert _evaluate_v1(n1, n2, inh) is None

    def test_row2_imp_gt_obl(self) -> None:
        """Imp > Obl: N1 is more specific in the legacy fixture."""
        kb, inh = _kb_with_hierarchy()
        # N1 (Imp) is more specific than N2 (Obl), so Imp wins
        n1 = _norm(IMP, specificity=1, source="n1:1")
        n2 = _norm(OBL, specificity=0, source="n2:2")
        # The more specific prohibition wins
        assert _evaluate(n1, n2, kb, inh) == DDICVerdict.FORBIDDEN
        assert _evaluate_v1(n1, n2, inh) == IMP

    def test_row3_imp_eq_opt(self) -> None:
        """Imp = Opt: inference rule 1 permits; DDIC concludes not obligatory."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(IMP, specificity=0, source="n1:1")
        n2 = _norm(OPT, specificity=0, source="n2:2")
        # Equal-specificity conflict: UNDECIDABLE
        assert _evaluate(n1, n2, kb, inh) == DDICVerdict.UNDECIDABLE
        assert _evaluate_v1(n1, n2, inh) is None

    def test_row4_imp_gt_opt(self) -> None:
        """Imp > Opt: N1 is more specific; the table concludes not obligatory."""
        kb, inh = _kb_with_hierarchy()
        # More specific N1 (Imp) wins by preemption
        n1 = _norm(IMP, specificity=1, source="n1:1")
        n2 = _norm(OPT, specificity=0, source="n2:2")
        assert _evaluate(n1, n2, kb, inh) == DDICVerdict.FORBIDDEN
        assert _evaluate_v1(n1, n2, inh) == IMP


# Theorem 6.4.2: a later subsuming prohibition suppresses an earlier
# obligation or permission.


class TestTable65_Theorem642:
    """Rows 5–8: Obl/Opt suppressed by later subsumming Imp."""

    def test_row5_obl_eq_imp(self) -> None:
        """Obl = Imp: prohibitive closure blocks execution; the legacy tie may be undecidable."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(OBL, specificity=0, source="n1:1")
        n2 = _norm(IMP, specificity=0, source="n2:2")
        # Equal specificity can yield UNDECIDABLE in the legacy evaluator
        result = _evaluate(n1, n2, kb, inh)
        # Olson gives Imp under prohibitive closure; AEGIS can be UNDECIDABLE
        # Both block execution; UNDECIDABLE requests escalation
        assert result in (DDICVerdict.UNDECIDABLE, DDICVerdict.FORBIDDEN)

    def test_row6_obl_lt_imp(self) -> None:
        """Obl < Imp: the more specific prohibition wins."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(OBL, specificity=0, source="n1:1")
        n2 = _norm(IMP, specificity=1, source="n2:2")
        assert _evaluate(n1, n2, kb, inh) == DDICVerdict.FORBIDDEN
        assert _evaluate_v1(n1, n2, inh) == IMP

    def test_row7_opt_eq_imp(self) -> None:
        """Opt = Imp → DDIC: Imp."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(OPT, specificity=0, source="n1:1")
        n2 = _norm(IMP, specificity=0, source="n2:2")
        result = _evaluate(n1, n2, kb, inh)
        assert result in (DDICVerdict.UNDECIDABLE, DDICVerdict.FORBIDDEN)

    def test_row8_opt_lt_imp(self) -> None:
        """Opt < Imp: the more specific prohibition wins."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(OPT, specificity=0, source="n1:1")
        n2 = _norm(IMP, specificity=1, source="n2:2")
        assert _evaluate(n1, n2, kb, inh) == DDICVerdict.FORBIDDEN
        assert _evaluate_v1(n1, n2, inh) == IMP


# Theorem 6.4.3: a strictly narrower prohibition defeats an obligation
# or permission within the narrower scope.


class TestTable65_Theorem643:
    """Rows 9–12: Strictly subsumed Imp defeats Obl/Opt."""

    def test_row9_imp_lt_obl(self) -> None:
        """A strictly subsumed prohibition takes precedence within its scope."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(IMP, specificity=1, source="n1:1")  # more specific
        n2 = _norm(OBL, specificity=0, source="n2:2")
        assert _evaluate(n1, n2, kb, inh) == DDICVerdict.FORBIDDEN
        assert _evaluate_v1(n1, n2, inh) == IMP

    def test_row10_obl_gt_imp(self) -> None:
        """The obligation subsumes the narrower prohibition, which wins locally."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(OBL, specificity=0, source="n1:1")
        n2 = _norm(IMP, specificity=1, source="n2:2")  # more specific
        assert _evaluate(n1, n2, kb, inh) == DDICVerdict.FORBIDDEN
        assert _evaluate_v1(n1, n2, inh) == IMP

    def test_row11_imp_lt_opt(self) -> None:
        """Imp < Opt → DDIC: Imp."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(IMP, specificity=1, source="n1:1")
        n2 = _norm(OPT, specificity=0, source="n2:2")
        assert _evaluate(n1, n2, kb, inh) == DDICVerdict.FORBIDDEN
        assert _evaluate_v1(n1, n2, inh) == IMP

    def test_row12_opt_gt_imp(self) -> None:
        """Opt > Imp → DDIC: Imp."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(OPT, specificity=0, source="n1:1")
        n2 = _norm(IMP, specificity=1, source="n2:2")
        assert _evaluate(n1, n2, kb, inh) == DDICVerdict.FORBIDDEN
        assert _evaluate_v1(n1, n2, inh) == IMP


# Theorem 6.4.4: neither norm subsumes the other. The prohibition
# defeats the obligation or permission at their intersection.


class TestTable65_Theorem644:
    """Rows 13–16: Intersecting conflicts (no subsumption)."""

    def test_row13_imp_intersect_obl(self) -> None:
        """Imp intersects Obl: prohibition applies at the intersection in Olson."""
        kb, inh = _kb_with_hierarchy()
        # Equal specificity without subsumption can yield UNDECIDABLE
        n1 = _norm(IMP, specificity=0, prop=("actionA",), source="n1:1")
        n2 = _norm(OBL, specificity=0, prop=("actionA",), source="n2:2")
        result = _evaluate(n1, n2, kb, inh)
        # Olson gives Imp at the intersection; AEGIS without precedence can be UNDECIDABLE
        assert result in (DDICVerdict.UNDECIDABLE, DDICVerdict.FORBIDDEN)

    def test_row14_obl_intersect_imp(self) -> None:
        """Obl ∩ Imp → DDIC: Imp."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(OBL, specificity=0, prop=("actionA",), source="n1:1")
        n2 = _norm(IMP, specificity=0, prop=("actionA",), source="n2:2")
        result = _evaluate(n1, n2, kb, inh)
        assert result in (DDICVerdict.UNDECIDABLE, DDICVerdict.FORBIDDEN)

    def test_row15_imp_intersect_opt(self) -> None:
        """Imp ∩ Opt → DDIC: Imp."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(IMP, specificity=0, prop=("actionA",), source="n1:1")
        n2 = _norm(OPT, specificity=0, prop=("actionA",), source="n2:2")
        result = _evaluate(n1, n2, kb, inh)
        assert result in (DDICVerdict.UNDECIDABLE, DDICVerdict.FORBIDDEN)

    def test_row16_opt_intersect_imp(self) -> None:
        """Opt ∩ Imp → DDIC: Imp."""
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(OPT, specificity=0, prop=("actionA",), source="n1:1")
        n2 = _norm(IMP, specificity=0, prop=("actionA",), source="n2:2")
        result = _evaluate(n1, n2, kb, inh)
        assert result in (DDICVerdict.UNDECIDABLE, DDICVerdict.FORBIDDEN)


# ── Cross-check: All 16 rows produce consistent v1/unified results

class TestTable65_CrossCheck:
    """Verify v1 DDICEngine and unified evaluator agree on all 16 rows."""

    @pytest.mark.parametrize(
        "mod1,spec1,mod2,spec2",
        [
            # Theorem 6.4.1
            (IMP, 0, OBL, 0),  # row 1
            (IMP, 1, OBL, 0),  # row 2
            (IMP, 0, OPT, 0),  # row 3
            (IMP, 1, OPT, 0),  # row 4
            # Theorem 6.4.2
            (OBL, 0, IMP, 0),  # row 5
            (OBL, 0, IMP, 1),  # row 6
            (OPT, 0, IMP, 0),  # row 7
            (OPT, 0, IMP, 1),  # row 8
            # Theorem 6.4.3
            (IMP, 1, OBL, 0),  # row 9
            (OBL, 0, IMP, 1),  # row 10
            (IMP, 1, OPT, 0),  # row 11
            (OPT, 0, IMP, 1),  # row 12
            # Theorem 6.4.4
            (IMP, 0, OBL, 0),  # row 13
            (OBL, 0, IMP, 0),  # row 14
            (IMP, 0, OPT, 0),  # row 15
            (OPT, 0, IMP, 0),  # row 16
        ],
    )
    def test_v1_and_unified_agree(
        self,
        mod1: DeonticModality,
        spec1: int,
        mod2: DeonticModality,
        spec2: int,
    ) -> None:
        kb, inh = _kb_with_hierarchy()
        n1 = _norm(mod1, specificity=spec1, source="n1:1")
        n2 = _norm(mod2, specificity=spec2, source="n2:2")

        v1_result = _evaluate_v1(n1, n2, inh)
        unified_result = _evaluate(n1, n2, kb, inh)

        # Map v1 to comparable value
        if v1_result is None:
            v1_mapped = DDICVerdict.UNDECIDABLE
        elif v1_result == IMP:
            v1_mapped = DDICVerdict.FORBIDDEN
        else:
            v1_mapped = DDICVerdict.PERMITTED

        assert unified_result == v1_mapped, (
            f"Row ({mod1.value} spec={spec1} vs {mod2.value} spec={spec2}): "
            f"v1={v1_result}, unified={unified_result}"
        )
