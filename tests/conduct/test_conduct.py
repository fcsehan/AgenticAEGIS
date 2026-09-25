"""Tests for CodeOfConduct, ConductRegistry, PrevalenceResolver, WRTEngine."""

from __future__ import annotations

from aegis.conduct.code_of_conduct import CodeOfConduct
from aegis.conduct.prevalence import PrevalenceResolver
from aegis.conduct.registry import ConductRegistry
from aegis.conduct.wrt import WRTEngine
from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.inheritance import InheritanceGraph
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


def _norm(
    modality: DeonticModality,
    agent: str = "*",
    code: str = "TestCode",
) -> NormFrame:
    return NormFrame(
        code=code,
        agent_pattern=agent,
        modality=modality,
        proposition=("action",),
    )


class TestCodeOfConduct:
    def test_add_norm(self) -> None:
        code = CodeOfConduct(name="TestCode")
        code.add_norm(_norm(DeonticModality.PERMITTED))
        assert len(code.norms) == 1

    def test_all_norms_includes_parent(self) -> None:
        parent = CodeOfConduct(name="Parent")
        parent.add_norm(_norm(DeonticModality.FORBIDDEN, code="Parent"))
        child = CodeOfConduct(name="Child", parent=parent)
        child.add_norm(_norm(DeonticModality.PERMITTED, code="Child"))
        assert len(child.all_norms()) == 2


class TestConductRegistry:
    def test_register_and_get(self) -> None:
        reg = ConductRegistry()
        code = CodeOfConduct(name="TestCode")
        reg.register(code)
        assert reg.get("TestCode") is code

    def test_from_kb(self) -> None:
        norms = [
            _norm(DeonticModality.PERMITTED, code="A"),
            _norm(DeonticModality.FORBIDDEN, code="B"),
        ]
        kb = KnowledgeBase()
        kb.create_mt("test")
        kb.freeze()
        reg = ConductRegistry.from_kb(kb, norms)
        assert len(reg) == 2
        assert "A" in reg.codes
        assert "B" in reg.codes

    def test_get_applicable(self) -> None:
        reg = ConductRegistry()
        code = CodeOfConduct(name="TestCode")
        code.add_norm(_norm(DeonticModality.PERMITTED, agent="agent-1"))
        reg.register(code)
        assert len(reg.get_applicable("agent-1")) == 1
        assert len(reg.get_applicable("agent-2")) == 0


class TestPrevalenceResolver:
    def test_higher_prevalence(self) -> None:
        codes = [
            CodeOfConduct(name="High", prevalence=0),
            CodeOfConduct(name="Low", prevalence=1),
        ]
        resolver = PrevalenceResolver(codes)
        assert resolver.higher_prevalence("High", "Low") == "High"

    def test_resolve(self) -> None:
        codes = [
            CodeOfConduct(name="A", prevalence=0),
            CodeOfConduct(name="B", prevalence=1),
        ]
        resolver = PrevalenceResolver(codes)
        winner = resolver.resolve(
            _norm(DeonticModality.PERMITTED, code="A"),
            _norm(DeonticModality.FORBIDDEN, code="B"),
        )
        assert winner is not None
        assert winner.code == "A"


class TestWRTEngine:
    def test_evaluate_wrt(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("test")
        kb.freeze()
        reasoner = BuiltinEngine(kb)
        reasoner.compute()
        graph = InheritanceGraph(reasoner)
        ddic = DDICEngine(graph)

        reg = ConductRegistry()
        code = CodeOfConduct(name="TestCode")
        code.add_norm(_norm(DeonticModality.PERMITTED, agent="agent"))
        reg.register(code)

        evaluator = WRTEngine(reg, ddic)
        status = evaluator.evaluate_wrt("TestCode", ("action",), "agent")
        assert status.is_permitted()

    def test_unknown_code(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("test")
        kb.freeze()
        reasoner = BuiltinEngine(kb)
        reasoner.compute()
        graph = InheritanceGraph(reasoner)
        ddic = DDICEngine(graph)
        reg = ConductRegistry()
        evaluator = WRTEngine(reg, ddic)
        status = evaluator.evaluate_wrt("UnknownCode", ("action",), "agent")
        assert status.is_undetermined()
