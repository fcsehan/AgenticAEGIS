"""Tests for ConfirmationPolicy data model (AEGIS-3301, Epic 33)."""

from __future__ import annotations

from aegis.orchestrator.confirmation_policy import (
    ConfirmationContext,
    ConfirmationDecision,
    ConfirmationPolicy,
    EchoFormat,
    TimeoutAction,
    TriggerCondition,
)


class TestShouldConfirm:
    def test_empty_triggers_never_fires(self) -> None:
        policy = ConfirmationPolicy()
        assert policy.should_confirm(
            frozenset({TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES}),
        ) is False

    def test_single_trigger_match(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
        )
        assert policy.should_confirm(
            frozenset({TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES}),
        ) is True

    def test_no_match_does_not_fire(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.VALIDATOR_DRIFT,),
        )
        assert policy.should_confirm(
            frozenset({TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES}),
        ) is False

    def test_multi_trigger_or_semantics(self) -> None:
        """Multiple triggers configured: any one of them firing is
        sufficient. Set-membership semantics, not all-of."""
        policy = ConfirmationPolicy(
            triggers=(
                TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,
                TriggerCondition.VALIDATOR_DRIFT,
            ),
        )
        # Only the second one is present in signals.
        assert policy.should_confirm(
            frozenset({TriggerCondition.VALIDATOR_DRIFT}),
        ) is True

    def test_empty_signals_never_fires(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
        )
        assert policy.should_confirm(frozenset()) is False


class TestIsAuthorized:
    def test_empty_principal_list_is_permissive(self) -> None:
        """Sane default for single-user dev/test contexts."""
        policy = ConfirmationPolicy()
        assert policy.is_authorized("anyone") is True

    def test_principal_in_list(self) -> None:
        policy = ConfirmationPolicy(authorized_principals=("J2", "J6"))
        assert policy.is_authorized("J2") is True

    def test_principal_not_in_list(self) -> None:
        policy = ConfirmationPolicy(authorized_principals=("J2",))
        assert policy.is_authorized("J6") is False

    def test_case_sensitive(self) -> None:
        """Principals are matched case-sensitively — J2 ≠ j2 to keep
        the contract precise."""
        policy = ConfirmationPolicy(authorized_principals=("J2",))
        assert policy.is_authorized("j2") is False


class TestPolicyImmutability:
    def test_policy_is_frozen(self) -> None:
        policy = ConfirmationPolicy()
        try:
            policy.timeout_seconds = 999  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("ConfirmationPolicy must be frozen")


class TestEnumCoverage:
    def test_trigger_condition_values_match_audit_codes(self) -> None:
        """Trigger enum values double as audit codes; verify the strings
        match the upstream conventions to prevent silent drift."""
        assert TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES.value == "MULTIPLE_MINIMAL_CANDIDATES"
        assert TriggerCondition.ACTION_SUBSTITUTION_DRIFT.value == "ACTION_SUBSTITUTION_DRIFT"

    def test_timeout_action_values(self) -> None:
        assert TimeoutAction.FAIL_CLOSED.value == "FAIL_CLOSED"
        assert TimeoutAction.ESCALATE_TO_REVIEWER.value == "ESCALATE_TO_REVIEWER"

    def test_echo_format_values(self) -> None:
        for fmt in (
            EchoFormat.PASSIVE_YES_NO,
            EchoFormat.ACTIVE_RESTATE,
            EchoFormat.EXPLICIT_SELECT,
        ):
            assert fmt.value == fmt.name


class TestContextAndDecision:
    def test_context_default_factories(self) -> None:
        ctx = ConfirmationContext(
            user_intent="x",
            proposed_action_type="y",
            proposed_action_description="z",
        )
        assert ctx.minimal_candidates == ()
        assert ctx.triggers == frozenset()
        assert ctx.confidence is None

    def test_decision_default(self) -> None:
        d = ConfirmationDecision(confirmed=True)
        assert d.response_text == ""
        assert d.selected_action_type == ""
        assert d.response_time_ms == 0
        assert d.principal == ""
