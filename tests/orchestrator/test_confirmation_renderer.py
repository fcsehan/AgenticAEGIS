"""Tests for confirmation renderer (AEGIS-3303, Epic 33)."""

from __future__ import annotations

from aegis.guard.registry import ActionTypeRegistry
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader
from aegis.orchestrator.confirmation_policy import (
    ConfirmationContext,
    ConfirmationPolicy,
    EchoFormat,
    TriggerCondition,
)
from aegis.orchestrator.confirmation_renderer import (
    ConfirmationView,
    render_confirmation_view,
    validate_active_restate,
)


def _registry_with_diagnosis() -> ActionTypeRegistry:
    kb = KnowledgeBase()
    loader = MeldLoader(kb)
    loader.load_string(
        """
        (case TestVocabMt)
        (isa readDiagnosis ActionType)
        (isa readPatientRecord ActionType)
        (actionDescription readDiagnosis "Reads only the diagnostic conclusion section.")
        (actionDescription readPatientRecord "Reads the entire patient record.")
        """,
        file="test.meld",
    )
    kb.freeze()
    return ActionTypeRegistry.from_kb(kb)


def _ctx_with_triggers(*triggers: TriggerCondition) -> ConfirmationContext:
    return ConfirmationContext(
        user_intent="show me the diagnosis",
        proposed_action_type="readDiagnosis",
        proposed_action_description="(filled in by the renderer)",
        triggers=frozenset(triggers),
    )


class TestRenderPassiveYesNo:
    def test_basic_view(self) -> None:
        policy = ConfirmationPolicy(echo_format=EchoFormat.PASSIVE_YES_NO)
        registry = _registry_with_diagnosis()
        ctx = _ctx_with_triggers(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES)

        view = render_confirmation_view(ctx, policy, registry)

        assert view.echo_format == EchoFormat.PASSIVE_YES_NO
        assert view.intent == "show me the diagnosis"
        assert view.proposed_action == "readDiagnosis"
        assert "Multiple candidate" in view.risk_summary
        assert view.alternatives == ()
        assert view.active_restate_hint == ""

    def test_description_pulled_from_registry(self) -> None:
        policy = ConfirmationPolicy(echo_format=EchoFormat.PASSIVE_YES_NO)
        registry = _registry_with_diagnosis()
        ctx = _ctx_with_triggers()

        view = render_confirmation_view(ctx, policy, registry)
        assert "diagnostic" in view.action_description.lower()


class TestRenderActiveRestate:
    def test_active_restate_hint_present(self) -> None:
        policy = ConfirmationPolicy(echo_format=EchoFormat.ACTIVE_RESTATE)
        registry = _registry_with_diagnosis()
        ctx = _ctx_with_triggers(TriggerCondition.VALIDATOR_DRIFT)

        view = render_confirmation_view(ctx, policy, registry)
        assert view.echo_format == EchoFormat.ACTIVE_RESTATE
        assert view.active_restate_hint
        assert "restate" in view.active_restate_hint.lower()


class TestRenderExplicitSelect:
    def test_alternatives_from_minimal_candidates(self) -> None:
        policy = ConfirmationPolicy(echo_format=EchoFormat.EXPLICIT_SELECT)
        registry = _registry_with_diagnosis()
        ctx = ConfirmationContext(
            user_intent="x",
            proposed_action_type="readDiagnosis",
            proposed_action_description="x",
            minimal_candidates=("readDiagnosis", "readPatientRecord"),
            triggers=frozenset({TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES}),
        )
        view = render_confirmation_view(ctx, policy, registry)
        assert view.alternatives == ("readDiagnosis", "readPatientRecord")

    def test_falls_back_to_proposed_action_if_no_candidates(self) -> None:
        policy = ConfirmationPolicy(echo_format=EchoFormat.EXPLICIT_SELECT)
        registry = _registry_with_diagnosis()
        ctx = _ctx_with_triggers()
        view = render_confirmation_view(ctx, policy, registry)
        assert view.alternatives == ("readDiagnosis",)


class TestRiskSummary:
    def test_no_triggers_default_summary(self) -> None:
        policy = ConfirmationPolicy()
        registry = _registry_with_diagnosis()
        ctx = ConfirmationContext(
            user_intent="x",
            proposed_action_type="readDiagnosis",
            proposed_action_description="x",
        )
        view = render_confirmation_view(ctx, policy, registry)
        assert "Confirmation requested." in view.risk_summary

    def test_multi_trigger_summary_concatenated(self) -> None:
        policy = ConfirmationPolicy()
        registry = _registry_with_diagnosis()
        ctx = _ctx_with_triggers(
            TriggerCondition.VALIDATOR_DRIFT,
            TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,
        )
        view = render_confirmation_view(ctx, policy, registry)
        assert "Multiple" in view.risk_summary
        assert "drift" in view.risk_summary.lower()


class TestRenderDeterminism:
    def test_same_inputs_produce_same_view(self) -> None:
        """AEGIS-3303 acceptance: snapshot-stable per format."""
        policy = ConfirmationPolicy(echo_format=EchoFormat.PASSIVE_YES_NO)
        registry = _registry_with_diagnosis()
        ctx = _ctx_with_triggers(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES)

        view_a = render_confirmation_view(ctx, policy, registry)
        view_b = render_confirmation_view(ctx, policy, registry)
        assert view_a == view_b


class TestActiveRestateValidation:
    def test_meaningful_restate_passes(self) -> None:
        assert validate_active_restate(
            "I want to read the diagnostic conclusion",
            "Reads only the diagnostic conclusion section.",
        ) is True

    def test_thin_yes_response_fails(self) -> None:
        assert validate_active_restate(
            "yes",
            "Reads only the diagnostic conclusion section.",
        ) is False

    def test_empty_response_fails(self) -> None:
        assert validate_active_restate(
            "",
            "Reads the diagnostic conclusion section.",
        ) is False

    def test_empty_description_fails(self) -> None:
        """No description = no anchor = cannot validate. Fail-closed."""
        assert validate_active_restate(
            "I want to read the diagnostic conclusion",
            "",
        ) is False

    def test_one_word_overlap_below_threshold(self) -> None:
        """Default minimum_overlap=2; one-word overlap is consent-theater."""
        assert validate_active_restate(
            "diagnostic something else entirely",
            "Reads only the diagnostic conclusion section.",
        ) is False

    def test_two_word_overlap_above_threshold(self) -> None:
        assert validate_active_restate(
            "diagnostic conclusion please",
            "Reads only the diagnostic conclusion section.",
        ) is True

    def test_overlap_ignores_short_words(self) -> None:
        """Short tokens (≤ 2 chars) don't count toward the overlap so
        articles / fillers can't pad the overlap count."""
        assert validate_active_restate(
            "I want to it of an or do",
            "I want to it of an or do",
        ) is False


class TestViewIsFrozen:
    def test_view_immutable(self) -> None:
        view = ConfirmationView(
            echo_format=EchoFormat.PASSIVE_YES_NO,
            intent="x",
            proposed_action="y",
            action_description="z",
            risk_summary="r",
        )
        try:
            view.intent = "changed"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("ConfirmationView must be frozen")
