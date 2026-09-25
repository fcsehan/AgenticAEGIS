"""Tests for ConfirmationGate (AEGIS-3302 + 3304, Epic 33)."""

from __future__ import annotations

from pathlib import Path

from aegis.audit.trail import AuditTrail
from aegis.guard.registry import ActionTypeRegistry
from aegis.guard.verdict import Decision, ReasonType
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader
from aegis.orchestrator.confirmation_gate import (
    ConfirmationGate,
    ConfirmationTimeout,
    GateOutcome,
)
from aegis.orchestrator.confirmation_policy import (
    ConfirmationContext,
    ConfirmationDecision,
    ConfirmationPolicy,
    EchoFormat,
    TimeoutAction,
    TriggerCondition,
)


def _registry() -> ActionTypeRegistry:
    kb = KnowledgeBase()
    loader = MeldLoader(kb)
    loader.load_string(
        """
        (case TestVocabMt)
        (isa readDiagnosis ActionType)
        (actionDescription readDiagnosis "Reads only the diagnostic conclusion section.")
        """,
        file="test.meld",
    )
    kb.freeze()
    return ActionTypeRegistry.from_kb(kb)


def _ctx() -> ConfirmationContext:
    return ConfirmationContext(
        user_intent="show me the diagnosis",
        proposed_action_type="readDiagnosis",
        proposed_action_description="(filled by renderer)",
        triggers=frozenset({TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES}),
    )


class TestPassThrough:
    def test_no_trigger_match_passes_through(self) -> None:
        policy = ConfirmationPolicy(triggers=())
        gate = ConfirmationGate(policy=policy, registry=_registry())
        result = gate.evaluate(_ctx())
        assert result.outcome == GateOutcome.PASS_THROUGH
        assert result.verdict is None


class TestConfirmedPath:
    def test_confirmed_passive_yesno(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
            echo_format=EchoFormat.PASSIVE_YES_NO,
        )
        gate = ConfirmationGate(policy=policy, registry=_registry())

        def callback(view):  # type: ignore[no-untyped-def]
            return ConfirmationDecision(confirmed=True, principal="user-1", response_time_ms=2_000)

        result = gate.evaluate(_ctx(), callback)
        assert result.outcome == GateOutcome.CONFIRMED
        assert result.verdict is None  # orchestrator continues
        assert result.decision is not None
        assert result.view is not None

    def test_confirmed_active_restate_with_overlap(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
            echo_format=EchoFormat.ACTIVE_RESTATE,
        )
        gate = ConfirmationGate(policy=policy, registry=_registry())

        def callback(view):  # type: ignore[no-untyped-def]
            return ConfirmationDecision(
                confirmed=True,
                principal="user-1",
                response_time_ms=5_000,
                response_text="diagnostic conclusion section read",
            )

        result = gate.evaluate(_ctx(), callback)
        assert result.outcome == GateOutcome.CONFIRMED


class TestRejectedPath:
    def test_explicit_decline(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
        )
        gate = ConfirmationGate(policy=policy, registry=_registry())

        def callback(view):  # type: ignore[no-untyped-def]
            return ConfirmationDecision(
                confirmed=False, principal="user-1", response_time_ms=3_000,
            )

        result = gate.evaluate(_ctx(), callback)
        assert result.outcome == GateOutcome.REJECTED
        assert result.verdict is not None
        assert result.verdict.decision == Decision.FORBIDDEN
        assert result.verdict.reason_type == ReasonType.USER_REJECTED

    def test_active_restate_with_thin_response_rejected(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
            echo_format=EchoFormat.ACTIVE_RESTATE,
        )
        gate = ConfirmationGate(policy=policy, registry=_registry())

        def callback(view):  # type: ignore[no-untyped-def]
            return ConfirmationDecision(
                confirmed=True,  # claims yes
                principal="user-1",
                response_time_ms=300,  # but very fast
                response_text="yes",  # and thin
            )

        result = gate.evaluate(_ctx(), callback)
        assert result.outcome == GateOutcome.REJECTED
        assert result.metadata["reason"] == "restate_overlap_too_low"


class TestTimeoutPath:
    def test_callback_raises_timeout_yields_undecidable(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
            timeout_seconds=10,
        )
        gate = ConfirmationGate(policy=policy, registry=_registry())

        def callback(view):  # type: ignore[no-untyped-def]
            raise ConfirmationTimeout

        result = gate.evaluate(_ctx(), callback)
        assert result.outcome == GateOutcome.TIMED_OUT
        assert result.verdict is not None
        assert result.verdict.decision == Decision.UNDECIDABLE
        assert result.verdict.reason_type == ReasonType.CONFIRMATION_TIMEOUT

    def test_no_callback_supplied_fails_closed(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
        )
        gate = ConfirmationGate(policy=policy, registry=_registry())
        result = gate.evaluate(_ctx())  # no callback
        assert result.outcome == GateOutcome.TIMED_OUT
        assert result.verdict is not None
        assert result.metadata["reason"] == "callback_missing"


class TestAuthorization:
    def test_unauthorized_principal_yields_unauthorized(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
            authorized_principals=("J2",),
            timeout_action=TimeoutAction.FAIL_CLOSED,
        )
        gate = ConfirmationGate(policy=policy, registry=_registry())

        def callback(view):  # type: ignore[no-untyped-def]
            return ConfirmationDecision(
                confirmed=True, principal="J6", response_time_ms=2_000,
            )

        result = gate.evaluate(_ctx(), callback)
        assert result.outcome == GateOutcome.UNAUTHORIZED
        assert result.verdict is not None
        assert result.verdict.reason_type == ReasonType.CONFIRMATION_PRINCIPAL_UNAUTHORIZED

    def test_unauthorized_with_escalate_policy_escalates(self) -> None:
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
            authorized_principals=("J2",),
            timeout_action=TimeoutAction.ESCALATE_TO_REVIEWER,
        )
        gate = ConfirmationGate(policy=policy, registry=_registry())

        def callback(view):  # type: ignore[no-untyped-def]
            return ConfirmationDecision(
                confirmed=True, principal="J6", response_time_ms=2_000,
            )

        result = gate.evaluate(_ctx(), callback)
        assert result.outcome == GateOutcome.ESCALATED
        # The verdict still reflects the unauthorized state — the
        # orchestrator decides whether to actually use the verdict
        # or hand off to a reviewer.
        assert result.verdict is not None


class TestAuditIntegration:
    def test_audit_lifecycle_written_on_confirmation(self, tmp_path: Path) -> None:
        audit_path = tmp_path / "audit.jsonl"
        trail = AuditTrail(audit_path)
        policy = ConfirmationPolicy(
            triggers=(TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,),
        )
        gate = ConfirmationGate(policy=policy, registry=_registry(), audit_trail=trail)

        def callback(view):  # type: ignore[no-untyped-def]
            return ConfirmationDecision(
                confirmed=True, principal="user-1", response_time_ms=3_000,
            )

        gate.evaluate(_ctx(), callback)
        import json
        records = [
            json.loads(line)
            for line in audit_path.read_text().splitlines()
            if line.strip()
        ]
        confirmations = [r for r in records if r["event"] == "CONFIRMATION_LIFECYCLE"]
        assert len(confirmations) == 1
        assert confirmations[0]["action"]["confirmed"] is True
        assert confirmations[0]["action"]["principal"] == "user-1"


class TestDomainDefaults:
    """AEGIS-3305: per-domain defaults wired to the gate."""

    def test_iamission_default_uses_active_restate(self) -> None:
        from aegis.orchestrator.confirmation_defaults import (
            IAMISSION_DEFAULT_POLICY,
            default_policy_for,
        )
        assert IAMISSION_DEFAULT_POLICY.echo_format == EchoFormat.ACTIVE_RESTATE
        assert IAMISSION_DEFAULT_POLICY.timeout_action == TimeoutAction.FAIL_CLOSED
        assert TriggerCondition.ACTION_SUBSTITUTION_DRIFT in IAMISSION_DEFAULT_POLICY.triggers

        # Lookup helper produces the same policy.
        assert default_policy_for("iamission") is IAMISSION_DEFAULT_POLICY

    def test_devops_default_is_lower_friction(self) -> None:
        from aegis.orchestrator.confirmation_defaults import DEVOPS_DEFAULT_POLICY
        assert DEVOPS_DEFAULT_POLICY.echo_format == EchoFormat.PASSIVE_YES_NO
        assert DEVOPS_DEFAULT_POLICY.timeout_seconds == 30

    def test_ifc_default_only_fires_on_multiple_minimal(self) -> None:
        from aegis.orchestrator.confirmation_defaults import IFC_DEFAULT_POLICY
        assert IFC_DEFAULT_POLICY.triggers == (TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,)

    def test_legal_default_escalates_on_timeout(self) -> None:
        from aegis.orchestrator.confirmation_defaults import LEGAL_DEFAULT_POLICY
        assert LEGAL_DEFAULT_POLICY.timeout_action == TimeoutAction.ESCALATE_TO_REVIEWER
        assert LEGAL_DEFAULT_POLICY.echo_format == EchoFormat.EXPLICIT_SELECT

    def test_unknown_domain_returns_disabled_policy(self) -> None:
        from aegis.orchestrator.confirmation_defaults import default_policy_for
        policy = default_policy_for("ghost-domain")
        assert policy.triggers == ()
        assert policy.should_confirm(
            frozenset({TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES}),
        ) is False
