"""AEGIS-1903: Axiom Monotonicity (I4).

Proves that moral axioms (defeasible=False) can never be defeated by
defeasible norms, regardless of specificity or quantity.

Invariant I4 (Olson): A non-defeasible norm is never preempted.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.inheritance import InheritanceGraph
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


def _make_engine(code_prevalence: list[str] | None = None) -> DDICEngine:
    kb = KnowledgeBase()
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    inheritance = InheritanceGraph(reasoner)
    return DDICEngine(inheritance, code_prevalence=code_prevalence)


@st.composite
def defeasible_norms_strategy(draw: Any) -> list[NormFrame]:
    """Generate 1-50 defeasible norms with PERMITTED modality."""
    count = draw(st.integers(min_value=1, max_value=50))
    norms: list[NormFrame] = []
    for i in range(count):
        norms.append(NormFrame(
            code=draw(st.sampled_from(["CodeA", "CodeB", "CodeC"])),
            agent_pattern="*",
            modality=DeonticModality.PERMITTED,
            proposition=("testAction",),
            specificity=draw(st.integers(min_value=0, max_value=100)),
            defeasible=True,
            source=f"defeasible-{i}",
        ))
    return norms


class TestAxiomMonotonicity:
    """Property: Moral axioms are never defeated by defeasible norms."""

    @given(defeasible_norms=defeasible_norms_strategy())
    @settings(max_examples=200, deadline=5000)
    def test_forbidden_axiom_never_becomes_permitted(
        self, defeasible_norms: list[NormFrame],
    ) -> None:
        """FORBIDDEN axiom + N defeasible PERMITTED → never PERMITTED."""
        engine = _make_engine(code_prevalence=["CodeA", "CodeB", "CodeC"])
        axiom = NormFrame(
            code="CodeA",
            agent_pattern="*",
            modality=DeonticModality.FORBIDDEN,
            proposition=("testAction",),
            specificity=0,
            defeasible=False,
            source="axiom-FORBIDDEN",
        )
        all_norms = [axiom] + defeasible_norms
        status = engine.evaluate(("testAction",), "*", all_norms)
        assert status.modality != DeonticModality.PERMITTED, (
            f"FORBIDDEN axiom was overridden to PERMITTED by {len(defeasible_norms)} "
            "defeasible norms"
        )

    @given(defeasible_norms=defeasible_norms_strategy())
    @settings(max_examples=200, deadline=5000)
    def test_permitted_axiom_never_becomes_forbidden(
        self, defeasible_norms: list[NormFrame],
    ) -> None:
        """PERMITTED axiom + N defeasible FORBIDDEN → never FORBIDDEN."""
        engine = _make_engine(code_prevalence=["CodeA", "CodeB", "CodeC"])
        # Make defeasible norms FORBIDDEN
        forbidden_norms = [
            NormFrame(
                code=n.code,
                agent_pattern=n.agent_pattern,
                modality=DeonticModality.FORBIDDEN,
                proposition=n.proposition,
                specificity=n.specificity,
                defeasible=True,
                source=n.source,
            )
            for n in defeasible_norms
        ]
        axiom = NormFrame(
            code="CodeA",
            agent_pattern="*",
            modality=DeonticModality.PERMITTED,
            proposition=("testAction",),
            specificity=0,
            defeasible=False,
            source="axiom-PERMITTED",
        )
        all_norms = [axiom] + forbidden_norms
        status = engine.evaluate(("testAction",), "*", all_norms)
        assert status.modality != DeonticModality.FORBIDDEN

    def test_higher_specificity_defeasible_cannot_defeat_axiom(self) -> None:
        """3 defeasible PERMITTED at specificity 10 vs 1 FORBIDDEN axiom at 0."""
        engine = _make_engine()
        axiom = NormFrame(
            code="Code",
            agent_pattern="*",
            modality=DeonticModality.FORBIDDEN,
            proposition=("act",),
            specificity=0,
            defeasible=False,
        )
        defeasibles = [
            NormFrame(
                code="Code",
                agent_pattern="*",
                modality=DeonticModality.PERMITTED,
                proposition=("act",),
                specificity=10 + i,
                defeasible=True,
            )
            for i in range(3)
        ]
        status = engine.evaluate(("act",), "*", [axiom] + defeasibles)
        assert status.modality == DeonticModality.FORBIDDEN
        assert status.reason == "moral_axiom"

    def test_contradictory_axioms_yield_undetermined(self) -> None:
        """PERMITTED axiom + FORBIDDEN axiom → UNDETERMINED."""
        engine = _make_engine()
        axiom_p = NormFrame(
            code="Code",
            agent_pattern="*",
            modality=DeonticModality.PERMITTED,
            proposition=("act",),
            specificity=0,
            defeasible=False,
        )
        axiom_f = NormFrame(
            code="Code",
            agent_pattern="*",
            modality=DeonticModality.FORBIDDEN,
            proposition=("act",),
            specificity=0,
            defeasible=False,
        )
        status = engine.evaluate(("act",), "*", [axiom_p, axiom_f])
        assert status.modality is None
        assert status.reason == "contradictory_axioms"
