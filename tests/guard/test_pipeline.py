"""Tests for EvaluationPipeline."""

from __future__ import annotations

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.inheritance import InheritanceGraph
from aegis.guard.action import Action
from aegis.guard.pipeline import EvaluationPipeline
from aegis.guard.registry import ActionTypeRegistry
from aegis.guard.verdict import Decision, ReasonType
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


def _setup() -> tuple[DDICEngine, ActionTypeRegistry, list[NormFrame]]:
    kb = KnowledgeBase()
    kb.create_mt("test")
    kb.assert_fact(("isa", "share", "MissionActionType"), "test")
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    graph = InheritanceGraph(reasoner)
    ddic = DDICEngine(graph)
    registry = ActionTypeRegistry.from_kb(kb)
    norms = [
        NormFrame(
            code="TestCode",
            agent_pattern="agent",
            modality=DeonticModality.PERMITTED,
            proposition=("share",),
            source="test:1",
        ),
    ]
    return ddic, registry, norms


class TestEvaluationPipeline:
    def test_permitted_action(self) -> None:
        ddic, registry, norms = _setup()
        pipeline = EvaluationPipeline(ddic, registry, norms)
        verdict = pipeline.run(
            Action(
                action_type="share",
                agent_id="agent",
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_invalid_action(self) -> None:
        ddic, registry, norms = _setup()
        pipeline = EvaluationPipeline(ddic, registry, norms)
        verdict = pipeline.run(
            Action(
                action_type="x" * 300,
                agent_id="agent",
            )
        )
        assert verdict.decision == Decision.UNDECIDABLE
        assert verdict.reason_type == ReasonType.INVALID_ACTION

    def test_no_jurisdiction(self) -> None:
        """Unknown action type → UNDECIDABLE (no jurisdiction)."""
        ddic, registry, norms = _setup()
        pipeline = EvaluationPipeline(ddic, registry, norms=[])
        verdict = pipeline.run(
            Action(
                action_type="unknownAction",
                agent_id="agent",
            )
        )
        assert verdict.decision == Decision.UNDECIDABLE

    def test_cwa_in_domain(self) -> None:
        """Known action type, no matching norms → FORBIDDEN (CWA)."""
        ddic, registry, norms = _setup()
        pipeline = EvaluationPipeline(ddic, registry, norms=[])
        verdict = pipeline.run(
            Action(
                action_type="share",  # known action type
                agent_id="agent",
            )
        )
        assert verdict.decision == Decision.FORBIDDEN
        assert verdict.reason_type == ReasonType.CWA_NO_PERMISSION

    def test_enricher_hook(self) -> None:
        """Enricher modifies context, not proposition."""
        ddic, registry, norms = _setup()

        def add_context(action: Action) -> Action:
            return Action(
                action_type=action.action_type,
                agent_id=action.agent_id,
                proposition=action.proposition,
                context={**action.context, "enriched": True},
            )

        pipeline = EvaluationPipeline(ddic, registry, norms, enrichers=[add_context])
        verdict = pipeline.run(Action(action_type="share", agent_id="agent"))
        assert verdict.decision == Decision.PERMITTED
