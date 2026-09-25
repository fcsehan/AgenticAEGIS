"""Equivalence tests: v1 DDICEngine vs. unified evaluate_legacy_module().

For every evaluation, the legacy DDICEngine and the new evaluate_legacy_module()
(operating on compiled DDICFormulas) must produce the same verdict.
"""

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


def _kb_with_hierarchy() -> KnowledgeBase:
    """Create a KB with a small agent hierarchy for specificity tests."""
    kb = KnowledgeBase()
    mt = "TestMt"
    kb.create_mt(mt)
    kb.assert_fact(("genls", "seniorAgent", "agent"), mt)
    kb.assert_fact(("genls", "juniorAgent", "agent"), mt)
    kb.assert_fact(("genls", "specialAgent", "seniorAgent"), mt)
    kb.freeze()
    return kb


def _inheritance(kb: KnowledgeBase) -> InheritanceGraph:
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return InheritanceGraph(reasoner)


def _v1_verdict_modality(
    engine: DDICEngine,
    norms: list[NormFrame],
    proposition: tuple[object, ...],
    agent: str,
) -> str | None:
    """Get the v1 verdict as a string for comparison."""
    status = engine.evaluate(proposition, agent, norms)
    if status.modality is None:
        return None
    return status.modality.value


def _unified_verdict(
    module: object,
    proposition: tuple[object, ...],
    agent: str,
    inheritance: InheritanceGraph | None = None,
) -> str | None:
    """Get the unified verdict as a string for comparison."""
    from aegis.engine.ddic_ir import DDICModule

    assert isinstance(module, DDICModule)
    state = evaluate_legacy_module(module, proposition, agent, inheritance)
    if state.verdict == DDICVerdict.PERMITTED:
        return "permitted"
    if state.verdict == DDICVerdict.FORBIDDEN:
        return "forbidden"
    return None  # UNDECIDABLE


# ── Equivalence Tests ───────────────────────────────────────────────


class TestSingleNormEquivalence:
    def test_single_forbidden(self) -> None:
        norms = [
            NormFrame(
                code="TestCode",
                agent_pattern="agent",
                modality=DeonticModality.FORBIDDEN,
                proposition=("doThing",),
                source="test:1",
            )
        ]
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        inh = _inheritance(kb)
        engine = DDICEngine(inh, code_prevalence=["TestCode"])
        module = compile_norms_to_module(norms, kb, code_prevalence=["TestCode"])

        v1 = _v1_verdict_modality(engine, norms, ("doThing",), "agent")
        v2 = _unified_verdict(module, ("doThing",), "agent", inh)

        assert v1 == "FORBIDDEN"
        assert v2 == "forbidden"

    def test_single_permitted(self) -> None:
        norms = [
            NormFrame(
                code="TestCode",
                agent_pattern="agent",
                modality=DeonticModality.PERMITTED,
                proposition=("doThing",),
                source="test:1",
            )
        ]
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        inh = _inheritance(kb)
        engine = DDICEngine(inh)
        module = compile_norms_to_module(norms, kb)

        v1 = _v1_verdict_modality(engine, norms, ("doThing",), "agent")
        v2 = _unified_verdict(module, ("doThing",), "agent", inh)

        assert v1 == "PERMITTED"
        assert v2 == "permitted"

    def test_single_obligatory(self) -> None:
        norms = [
            NormFrame(
                code="TestCode",
                agent_pattern="agent",
                modality=DeonticModality.OBLIGATORY,
                proposition=("doThing",),
                source="test:1",
            )
        ]
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        inh = _inheritance(kb)
        engine = DDICEngine(inh)
        module = compile_norms_to_module(norms, kb)

        v1 = _v1_verdict_modality(engine, norms, ("doThing",), "agent")
        v2 = _unified_verdict(module, ("doThing",), "agent", inh)

        assert v1 == "OBLIGATORY"
        assert v2 == "permitted"  # OBLIGATORY → PERMITTED in unified output


class TestNoApplicableNorms:
    def test_no_matching_agent(self) -> None:
        norms = [
            NormFrame(
                code="C", agent_pattern="otherAgent",
                modality=DeonticModality.FORBIDDEN,
                proposition=("doThing",), source="test:1",
            )
        ]
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        inh = _inheritance(kb)
        engine = DDICEngine(inh)
        module = compile_norms_to_module(norms, kb)

        v1 = _v1_verdict_modality(engine, norms, ("doThing",), "agent")
        v2 = _unified_verdict(module, ("doThing",), "agent", inh)

        assert v1 is None
        assert v2 is None

    def test_no_matching_proposition(self) -> None:
        norms = [
            NormFrame(
                code="C", agent_pattern="agent",
                modality=DeonticModality.FORBIDDEN,
                proposition=("doOtherThing",), source="test:1",
            )
        ]
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        inh = _inheritance(kb)
        engine = DDICEngine(inh)
        module = compile_norms_to_module(norms, kb)

        v1 = _v1_verdict_modality(engine, norms, ("doThing",), "agent")
        v2 = _unified_verdict(module, ("doThing",), "agent", inh)

        assert v1 is None
        assert v2 is None


class TestMoralAxiom:
    def test_axiom_wins_over_defeasible(self) -> None:
        norms = [
            NormFrame(
                code="C", agent_pattern="agent",
                modality=DeonticModality.FORBIDDEN,
                proposition=("doThing",), defeasible=False, source="axiom:1",
            ),
            NormFrame(
                code="C", agent_pattern="agent",
                modality=DeonticModality.PERMITTED,
                proposition=("doThing",), defeasible=True, source="rule:2",
            ),
        ]
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        inh = _inheritance(kb)
        engine = DDICEngine(inh)
        module = compile_norms_to_module(norms, kb)

        v1 = _v1_verdict_modality(engine, norms, ("doThing",), "agent")
        v2 = _unified_verdict(module, ("doThing",), "agent", inh)

        assert v1 == "FORBIDDEN"
        assert v2 == "forbidden"


class TestConflictResolution:
    def test_unresolvable_conflict(self) -> None:
        norms = [
            NormFrame(
                code="A", agent_pattern="agent",
                modality=DeonticModality.FORBIDDEN,
                proposition=("doThing",), source="a:1",
            ),
            NormFrame(
                code="A", agent_pattern="agent",
                modality=DeonticModality.PERMITTED,
                proposition=("doThing",), source="a:2",
            ),
        ]
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        inh = _inheritance(kb)
        engine = DDICEngine(inh)
        module = compile_norms_to_module(norms, kb)

        v1 = _v1_verdict_modality(engine, norms, ("doThing",), "agent")
        v2 = _unified_verdict(module, ("doThing",), "agent", inh)

        # Both should be undetermined/undecidable
        assert v1 is None
        assert v2 is None

    def test_code_prevalence_resolves(self) -> None:
        norms = [
            NormFrame(
                code="HighCode", agent_pattern="agent",
                modality=DeonticModality.FORBIDDEN,
                proposition=("doThing",), source="high:1",
            ),
            NormFrame(
                code="LowCode", agent_pattern="agent",
                modality=DeonticModality.PERMITTED,
                proposition=("doThing",), source="low:2",
            ),
        ]
        prevalence = ["HighCode", "LowCode"]
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        inh = _inheritance(kb)
        engine = DDICEngine(inh, code_prevalence=prevalence)
        module = compile_norms_to_module(norms, kb, code_prevalence=prevalence)

        v1 = _v1_verdict_modality(engine, norms, ("doThing",), "agent")
        v2 = _unified_verdict(module, ("doThing",), "agent", inh)

        assert v1 == "FORBIDDEN"
        assert v2 == "forbidden"


class TestCompoundProposition:
    def test_compound_match(self) -> None:
        norms = [
            NormFrame(
                code="C", agent_pattern="agent",
                modality=DeonticModality.FORBIDDEN,
                proposition=("shareIntel", "classified"),
                source="test:1",
            )
        ]
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        inh = _inheritance(kb)
        engine = DDICEngine(inh)
        module = compile_norms_to_module(norms, kb)

        v1 = _v1_verdict_modality(engine, norms, ("shareIntel", "classified"), "agent")
        v2 = _unified_verdict(module, ("shareIntel", "classified"), "agent", inh)

        assert v1 == "FORBIDDEN"
        assert v2 == "forbidden"

    def test_prefix_match(self) -> None:
        norms = [
            NormFrame(
                code="C", agent_pattern="agent",
                modality=DeonticModality.FORBIDDEN,
                proposition=("shareIntel",),
                source="test:1",
            )
        ]
        kb = KnowledgeBase()
        kb.create_mt("T")
        kb.freeze()
        inh = _inheritance(kb)
        engine = DDICEngine(inh)
        module = compile_norms_to_module(norms, kb)

        v1 = _v1_verdict_modality(
            engine, norms, ("shareIntel", "classified", "ext"), "agent"
        )
        v2 = _unified_verdict(
            module, ("shareIntel", "classified", "ext"), "agent", inh
        )

        assert v1 == "FORBIDDEN"
        assert v2 == "forbidden"
