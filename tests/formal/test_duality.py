"""AEGIS-1905: Duality Invariant (I7).

``forbidden(AGT, PROP) ↔ ¬permitted(AGT, PROP)``

Tests that flipping a norm's modality from FORBIDDEN to PERMITTED (or
vice versa) always changes the evaluation outcome, confirming the
deontic duality.
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

P = DeonticModality.PERMITTED
F = DeonticModality.FORBIDDEN
O = DeonticModality.OBLIGATORY


def _make_engine() -> DDICEngine:
    kb = KnowledgeBase()
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    inheritance = InheritanceGraph(reasoner)
    return DDICEngine(inheritance)


class TestDuality:
    """Duality: FORBIDDEN ↔ ¬PERMITTED."""

    def test_single_forbidden_flipped_to_permitted(self) -> None:
        """Single FORBIDDEN norm → FORBIDDEN. Flip → PERMITTED."""
        engine = _make_engine()
        norm_f = NormFrame(
            code="Code", agent_pattern="*", modality=F,
            proposition=("act",), defeasible=True,
        )
        norm_p = NormFrame(
            code="Code", agent_pattern="*", modality=P,
            proposition=("act",), defeasible=True,
        )
        status_f = engine.evaluate(("act",), "*", [norm_f])
        status_p = engine.evaluate(("act",), "*", [norm_p])
        assert status_f.modality == F
        assert status_p.modality == P

    def test_single_permitted_flipped_to_forbidden(self) -> None:
        """Single PERMITTED norm → PERMITTED. Flip → FORBIDDEN."""
        engine = _make_engine()
        norm_p = NormFrame(
            code="Code", agent_pattern="*", modality=P,
            proposition=("act",), defeasible=True,
        )
        norm_f = NormFrame(
            code="Code", agent_pattern="*", modality=F,
            proposition=("act",), defeasible=True,
        )
        status_p = engine.evaluate(("act",), "*", [norm_p])
        status_f = engine.evaluate(("act",), "*", [norm_f])
        assert status_p.modality == P
        assert status_f.modality == F

    @given(
        specificity=st.integers(min_value=0, max_value=50),
        code=st.sampled_from(["CodeA", "CodeB"]),
    )
    @settings(max_examples=100, deadline=5000)
    def test_modality_flip_changes_outcome(
        self, specificity: int, code: str,
    ) -> None:
        """For any single norm, flipping P↔F always changes the result."""
        engine = _make_engine()
        norm_p = NormFrame(
            code=code, agent_pattern="*", modality=P,
            proposition=("act",), specificity=specificity, defeasible=True,
        )
        norm_f = NormFrame(
            code=code, agent_pattern="*", modality=F,
            proposition=("act",), specificity=specificity, defeasible=True,
        )
        status_p = engine.evaluate(("act",), "*", [norm_p])
        status_f = engine.evaluate(("act",), "*", [norm_f])
        assert status_p.modality != status_f.modality, (
            f"Flipping modality should change outcome, "
            f"got P={status_p.modality}, F={status_f.modality}"
        )

    def test_negation_preds_consistency(self) -> None:
        """negationPreds: oughtToDo↔forbiddenToDo, permittedToDo↔forbiddenToDo."""
        assert O.negation() == F
        assert F.negation() == P
        assert P.negation() == F

    def test_conflicts_with_is_symmetric(self) -> None:
        """conflicts_with(a, b) ↔ conflicts_with(b, a)."""
        norm_p = NormFrame(
            code="Code", agent_pattern="*", modality=P,
            proposition=("act",), defeasible=True,
        )
        norm_f = NormFrame(
            code="Code", agent_pattern="*", modality=F,
            proposition=("act",), defeasible=True,
        )
        assert norm_p.conflicts_with(norm_f) == norm_f.conflicts_with(norm_p)
        assert norm_p.conflicts_with(norm_f) is True

    def test_obligatory_does_not_conflict_with_permitted(self) -> None:
        """OBLIGATORY implies PERMITTED — they don't conflict."""
        norm_o = NormFrame(
            code="Code", agent_pattern="*", modality=O,
            proposition=("act",), defeasible=True,
        )
        norm_p = NormFrame(
            code="Code", agent_pattern="*", modality=P,
            proposition=("act",), defeasible=True,
        )
        assert not norm_o.conflicts_with(norm_p)
        assert not norm_p.conflicts_with(norm_o)
