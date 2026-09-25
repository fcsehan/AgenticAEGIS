"""Tests for AEGIS-1705: Transformation Policy Engine."""

from __future__ import annotations

from unittest.mock import MagicMock

from aegis.guard.action import Action
from aegis.guard.verdict import Decision, ReasonType, Verdict
from aegis.ifc.transform_policy import TransformPolicy


def _make_verdict(decision: Decision) -> Verdict:
    return Verdict(
        decision=decision,
        reason_type=ReasonType.EXPLICIT_NORM,
        justification_chain=("test",),
        action_type="summarizeInformation",
        agent_id="test",
    )


class TestTransformPolicy:
    def test_summarize_public_permitted(self) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.PERMITTED)

        engine = TransformPolicy(guard)
        verdict = engine.check_transformation(
            transformation_type="summarization",
            source_classifications=["public"],
            target_classification="public",
            target_recipient="internalAgent",
            agent_id="agent-1",
        )

        assert verdict.decision == Decision.PERMITTED
        action = guard.check.call_args[0][0]
        assert action.action_type == "summarizeInformation"
        assert action.proposition["sourceClassification"] == "public"
        assert action.proposition["targetClassification"] == "public"
        assert action.proposition["recipient"] == "internalAgent"

    def test_summarize_secret_to_public_forbidden(self) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.FORBIDDEN)

        engine = TransformPolicy(guard)
        verdict = engine.check_transformation(
            transformation_type="summarization",
            source_classifications=["secret"],
            target_classification="public",
            target_recipient="externalService",
            agent_id="agent-1",
        )

        assert verdict.decision == Decision.FORBIDDEN

    def test_reclassification_uses_classify_action(self) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.FORBIDDEN)

        engine = TransformPolicy(guard)
        engine.check_transformation(
            transformation_type="reclassification",
            source_classifications=["secret"],
            target_classification="public",
            target_recipient="externalService",
            agent_id="agent-1",
        )

        action = guard.check.call_args[0][0]
        assert action.action_type == "classifyInformation"
        assert "recipient" not in action.proposition
        assert action.proposition["sourceClassification"] == "secret"
        assert action.proposition["targetClassification"] == "public"

    def test_highest_classification_used(self) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.FORBIDDEN)

        engine = TransformPolicy(guard)
        engine.check_transformation(
            transformation_type="summarization",
            source_classifications=["public", "secret", "internal"],
            target_classification="public",
            target_recipient="externalService",
            agent_id="agent-1",
        )

        action = guard.check.call_args[0][0]
        assert action.proposition["sourceClassification"] == "secret"

    def test_extraction_maps_correctly(self) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.PERMITTED)

        engine = TransformPolicy(guard)
        engine.check_transformation(
            transformation_type="extraction",
            source_classifications=["internal"],
            target_classification="internal",
            target_recipient="internalAgent",
            agent_id="agent-1",
        )

        action = guard.check.call_args[0][0]
        assert action.action_type == "extractFacts"
