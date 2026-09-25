"""Tests for the DDIC Engine — heartpiece of AEGIS."""

from __future__ import annotations

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.inheritance import InheritanceGraph
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


def _simple_graph() -> InheritanceGraph:
    kb = KnowledgeBase()
    kb.create_mt("test")
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return InheritanceGraph(reasoner)


def _norm(
    modality: DeonticModality,
    agent: str = "*",
    code: str = "TestCode",
    specificity: int = 0,
    defeasible: bool = True,
) -> NormFrame:
    return NormFrame(
        code=code,
        agent_pattern=agent,
        modality=modality,
        proposition=("action",),
        specificity=specificity,
        defeasible=defeasible,
        source="test",
    )


class TestDDICEngine:
    def test_single_permitted(self) -> None:
        engine = DDICEngine(_simple_graph())
        status = engine.evaluate(
            proposition=("action",),
            agent="agent",
            norms=[_norm(DeonticModality.PERMITTED, agent="agent")],
        )
        assert status.is_permitted()

    def test_single_forbidden(self) -> None:
        engine = DDICEngine(_simple_graph())
        status = engine.evaluate(
            proposition=("action",),
            agent="agent",
            norms=[_norm(DeonticModality.FORBIDDEN, agent="agent")],
        )
        assert status.is_forbidden()

    def test_no_norms_undetermined(self) -> None:
        engine = DDICEngine(_simple_graph())
        status = engine.evaluate(
            proposition=("action",),
            agent="agent",
            norms=[],
        )
        assert status.is_undetermined()

    def test_moral_axiom_wins(self) -> None:
        """Non-defeasible axiom overrides everything."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(DeonticModality.PERMITTED, agent="agent", specificity=5),
            _norm(DeonticModality.FORBIDDEN, agent="agent", defeasible=False),
        ]
        status = engine.evaluate(("action",), "agent", norms)
        assert status.is_forbidden()
        assert status.reason == "moral_axiom"

    def test_specificity_wins(self) -> None:
        """More specific norm overrides less specific."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(DeonticModality.FORBIDDEN, agent="agent", specificity=1),
            _norm(DeonticModality.PERMITTED, agent="agent", specificity=3),
        ]
        status = engine.evaluate(("action",), "agent", norms)
        assert status.is_permitted()
        assert status.reason == "specificity"

    def test_cross_code_prevalence(self) -> None:
        """Higher-prevalence code wins when same specificity."""
        engine = DDICEngine(
            _simple_graph(),
            code_prevalence=["HighCode", "LowCode"],
        )
        norms = [
            _norm(DeonticModality.PERMITTED, agent="agent", code="LowCode"),
            _norm(DeonticModality.FORBIDDEN, agent="agent", code="HighCode"),
        ]
        status = engine.evaluate(("action",), "agent", norms)
        assert status.is_forbidden()
        assert status.reason == "cross_code_prevalence"

    def test_unresolvable_conflict(self) -> None:
        """Same code, same specificity, no prevalence → undetermined."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(DeonticModality.PERMITTED, agent="agent", code="Same"),
            _norm(DeonticModality.FORBIDDEN, agent="agent", code="Same"),
        ]
        status = engine.evaluate(("action",), "agent", norms)
        assert status.is_undetermined()
        assert status.reason == "unresolved_conflict"

    def test_agent_filtering(self) -> None:
        """Norms for different agents are filtered out."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(DeonticModality.FORBIDDEN, agent="other-agent"),
            _norm(DeonticModality.PERMITTED, agent="my-agent"),
        ]
        status = engine.evaluate(("action",), "my-agent", norms)
        assert status.is_permitted()

    def test_deterministic(self) -> None:
        """Same inputs → same outputs (I1)."""
        engine = DDICEngine(_simple_graph(), code_prevalence=["A", "B"])
        norms = [
            _norm(DeonticModality.PERMITTED, agent="a", code="A", specificity=1),
            _norm(DeonticModality.FORBIDDEN, agent="a", code="B", specificity=2),
        ]
        results = [engine.evaluate(("act",), "a", norms) for _ in range(100)]
        assert all(r.modality == results[0].modality for r in results)
