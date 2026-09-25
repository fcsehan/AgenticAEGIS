"""Tests for the MELD/DDIC v2 guard pipeline."""

from __future__ import annotations

from pathlib import Path

from aegis.engine.ddic_ir import compile_meld_module
from aegis.guard.action import Action
from aegis.guard.ddic_pipeline import DDICEvaluationPipeline
from aegis.guard.registry import ActionTypeRegistry
from aegis.guard.verdict import Decision, ReasonType
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import parse_meld, parse_meld_module


def _build_registry_from_v2(text: str, file: str = "pipeline-v2.meld") -> ActionTypeRegistry:
    kb = KnowledgeBase()
    current_mt: str | None = None
    for assertion in parse_meld(text, file):
        predicate = assertion[0] if assertion else None
        if predicate == "case":
            current_mt = str(assertion[1])
            if kb.get_mt(current_mt) is None:
                kb.create_mt(current_mt)
            continue
        if predicate == "aegis-schema-version":
            continue
        if current_mt is None:
            raise AssertionError("test fixture missing case statement")
        kb.assert_fact(assertion, current_mt)
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return ActionTypeRegistry.from_kb(kb)


class TestDDICEvaluationPipeline:
    def test_permitted_action_from_active_belief(self) -> None:
        text = """
        (aegis-schema-version 2)
        (case OlsonDDICMt)
        (isa shareWeather MissionActionType)
        (belief-optional AgentA shareWeather Public tn)
        """
        pipeline = DDICEvaluationPipeline(
            module=compile_meld_module(parse_meld_module(text, file="v2-permitted.meld")),
            registry=_build_registry_from_v2(text, file="v2-permitted.meld"),
        )

        verdict = pipeline.run(
            Action(action_type="shareWeather", agent_id="AgentA", context={"ddic_context": "Public"})
        )

        assert verdict.decision == Decision.PERMITTED
        assert verdict.reason_type == ReasonType.EXPLICIT_NORM

    def test_known_action_without_matching_belief_is_cwa_forbidden(self) -> None:
        text = """
        (aegis-schema-version 2)
        (case OlsonDDICMt)
        (isa shareWeather MissionActionType)
        """
        pipeline = DDICEvaluationPipeline(
            module=compile_meld_module(parse_meld_module(text, file="v2-cwa.meld")),
            registry=_build_registry_from_v2(text, file="v2-cwa.meld"),
        )

        verdict = pipeline.run(Action(action_type="shareWeather", agent_id="AgentA"))

        assert verdict.decision == Decision.FORBIDDEN
        assert verdict.reason_type == ReasonType.CWA_NO_PERMISSION

    def test_unknown_action_without_jurisdiction_is_undecidable(self) -> None:
        text = """
        (aegis-schema-version 2)
        (case OlsonDDICMt)
        (isa shareWeather MissionActionType)
        """
        pipeline = DDICEvaluationPipeline(
            module=compile_meld_module(parse_meld_module(text, file="v2-no-jurisdiction.meld")),
            registry=_build_registry_from_v2(text, file="v2-no-jurisdiction.meld"),
        )

        verdict = pipeline.run(Action(action_type="deleteWeather", agent_id="AgentA"))

        assert verdict.decision == Decision.UNDECIDABLE
        assert verdict.reason_type == ReasonType.NO_JURISDICTION
