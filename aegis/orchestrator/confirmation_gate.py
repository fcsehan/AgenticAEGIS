"""User-Confirmation-Loop gate component (AEGIS-3302 + 3304, Epic 33).

Glues the policy (AEGIS-3301), the renderer (AEGIS-3303) and the
audit trail (AEGIS-3306) together into a single orchestrator-callable
component. The orchestrator hands the gate a ``ConfirmationContext``
plus a ``ConfirmationDecision``-callback (the I/O bridge); the gate
returns a ``GateResult`` describing what the orchestrator should do
next.

The gate itself is *transport-agnostic*. It does not implement the
prompt UI or the timeout-clock — those belong to the frontend (CLI,
IDE, web). The gate's job is the policy logic:

- Should we ask? (trigger evaluation)
- Is the principal allowed to answer? (authorization)
- Did the answer satisfy the echo format? (validation)
- What verdict-side outcome should the orchestrator surface?

Per AEGIS-3304 the gate also implements the escalation path: when
the principal is not on the authorized list, the gate emits an
ESCALATE result so the orchestrator can hand off to a configured
reviewer rather than silently failing closed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from aegis.audit.trail import AuditTrail
from aegis.guard.registry import ActionTypeRegistry
from aegis.guard.verdict import Decision, ReasonType, Verdict
from aegis.orchestrator.confirmation_policy import (
    ConfirmationContext,
    ConfirmationDecision,
    ConfirmationPolicy,
    EchoFormat,
    TimeoutAction,
)
from aegis.orchestrator.confirmation_renderer import (
    ConfirmationView,
    render_confirmation_view,
    validate_active_restate,
)


class GateOutcome(Enum):
    """Outcome produced by the gate. The orchestrator dispatches on this."""

    PASS_THROUGH = "PASS_THROUGH"
    """No confirmation required; original action proceeds."""

    CONFIRMED = "CONFIRMED"
    """User confirmed; original action proceeds."""

    REJECTED = "REJECTED"
    """User declined; verdict surfaces as FORBIDDEN/USER_REJECTED."""

    TIMED_OUT = "TIMED_OUT"
    """No response in time. Verdict reflects the policy's timeout_action."""

    UNAUTHORIZED = "UNAUTHORIZED"
    """The principal who answered is not on the authorized list."""

    ESCALATED = "ESCALATED"
    """Authorization failed; the orchestrator should hand off to a reviewer."""


@dataclass(frozen=True, slots=True)
class GateResult:
    """The gate's recommendation back to the orchestrator."""

    outcome: GateOutcome
    verdict: Verdict | None = None
    """Set when outcome ∈ {REJECTED, TIMED_OUT, UNAUTHORIZED}; otherwise
    None (the orchestrator continues with its existing verdict path)."""

    view: ConfirmationView | None = None
    """The rendered prompt view, when one was produced. Useful for
    audit-side replay and debugging."""

    decision: ConfirmationDecision | None = None
    """The user's response, when one was collected."""

    metadata: dict[str, str] = field(default_factory=dict)
    """Free-form annotations for audit. Always populated when outcome ≠
    PASS_THROUGH."""


# Type alias for the I/O bridge: given a rendered view, produce the
# user's response. The orchestrator is responsible for clock+timeout
# enforcement; the bridge raises ``ConfirmationTimeout`` when the
# user does not respond within the policy's timeout_seconds.
DecisionCallback = Callable[[ConfirmationView], ConfirmationDecision]


class ConfirmationTimeout(TimeoutError):
    """Signal raised by a DecisionCallback when the user does not answer
    within the policy timeout. The gate translates this into the
    ``TIMED_OUT`` outcome with the policy's ``timeout_action``
    semantics."""


class ConfirmationGate:
    """The User-Confirmation-Loop policy gate.

    Construct once per orchestrator session; reuse across many
    confirmation cycles. Thread-safe is *not* claimed — the gate
    inherits the orchestrator's threading model.
    """

    def __init__(
        self,
        policy: ConfirmationPolicy,
        registry: ActionTypeRegistry,
        *,
        audit_trail: AuditTrail | None = None,
    ) -> None:
        self._policy = policy
        self._registry = registry
        self._audit = audit_trail

    def evaluate(
        self,
        context: ConfirmationContext,
        callback: DecisionCallback | None = None,
    ) -> GateResult:
        """Run one cycle of the gate.

        Args:
            context: orchestrator state at the trigger point.
            callback: I/O bridge that turns the rendered view into a
                ``ConfirmationDecision``. Required when triggers fire;
                irrelevant when no trigger matches.
        """
        if not self._policy.should_confirm(context.triggers):
            return GateResult(outcome=GateOutcome.PASS_THROUGH)

        view = render_confirmation_view(context, self._policy, self._registry)

        if callback is None:
            # Orchestrator tried to evaluate without supplying an I/O
            # bridge — fail-closed.
            verdict = self._fail_closed_verdict(
                context,
                reason=ReasonType.CONFIRMATION_TIMEOUT,
                explanation="No DecisionCallback supplied to ConfirmationGate.",
            )
            self._audit_lifecycle(context, view, decision=None, outcome=GateOutcome.TIMED_OUT)
            return GateResult(
                outcome=GateOutcome.TIMED_OUT,
                verdict=verdict,
                view=view,
                metadata={"reason": "callback_missing"},
            )

        try:
            decision = callback(view)
        except ConfirmationTimeout:
            return self._handle_timeout(context, view)

        return self._handle_decision(context, view, decision)

    # ── Helper paths ────────────────────────────────────────────────

    def _handle_decision(
        self,
        context: ConfirmationContext,
        view: ConfirmationView,
        decision: ConfirmationDecision,
    ) -> GateResult:
        if not self._policy.is_authorized(decision.principal):
            verdict = self._fail_closed_verdict(
                context,
                reason=ReasonType.CONFIRMATION_PRINCIPAL_UNAUTHORIZED,
                explanation=(
                    f"principal {decision.principal!r} is not on the "
                    f"authorized list for domain {self._policy.domain!r}"
                ),
            )
            self._audit_lifecycle(
                context, view, decision=decision,
                outcome=GateOutcome.UNAUTHORIZED,
            )
            # The orchestrator decides whether to escalate or hard-fail
            # based on the policy's TimeoutAction analogue. Default
            # is hard-fail (UNAUTHORIZED); when the policy is
            # configured to escalate via ESCALATE_TO_REVIEWER, switch
            # the outcome.
            outcome = (
                GateOutcome.ESCALATED
                if self._policy.timeout_action == TimeoutAction.ESCALATE_TO_REVIEWER
                else GateOutcome.UNAUTHORIZED
            )
            return GateResult(
                outcome=outcome, verdict=verdict, view=view, decision=decision,
                metadata={"reason": "principal_not_authorized"},
            )

        if not decision.confirmed:
            verdict = self._fail_closed_verdict(
                context,
                reason=ReasonType.USER_REJECTED,
                explanation="user declined the confirmation prompt",
            )
            self._audit_lifecycle(
                context, view, decision=decision, outcome=GateOutcome.REJECTED,
            )
            return GateResult(
                outcome=GateOutcome.REJECTED, verdict=verdict, view=view,
                decision=decision,
            )

        # Confirmed — but for ACTIVE_RESTATE we additionally check the
        # word-overlap on the response_text.
        if (
            self._policy.echo_format == EchoFormat.ACTIVE_RESTATE
            and not validate_active_restate(
                decision.response_text, view.action_description,
            )
        ):
            verdict = self._fail_closed_verdict(
                context,
                reason=ReasonType.USER_REJECTED,
                explanation="restate response did not overlap with the action description",
            )
            self._audit_lifecycle(
                context, view, decision=decision, outcome=GateOutcome.REJECTED,
            )
            return GateResult(
                outcome=GateOutcome.REJECTED, verdict=verdict, view=view,
                decision=decision,
                metadata={"reason": "restate_overlap_too_low"},
            )

        self._audit_lifecycle(
            context, view, decision=decision, outcome=GateOutcome.CONFIRMED,
        )
        return GateResult(
            outcome=GateOutcome.CONFIRMED, view=view, decision=decision,
        )

    def _handle_timeout(
        self,
        context: ConfirmationContext,
        view: ConfirmationView,
    ) -> GateResult:
        verdict = self._fail_closed_verdict(
            context,
            reason=ReasonType.CONFIRMATION_TIMEOUT,
            explanation=(
                f"user did not respond within {self._policy.timeout_seconds}s"
            ),
        )
        self._audit_lifecycle(
            context, view, decision=None, outcome=GateOutcome.TIMED_OUT,
        )
        return GateResult(
            outcome=GateOutcome.TIMED_OUT, verdict=verdict, view=view,
            metadata={"reason": "timeout"},
        )

    def _fail_closed_verdict(
        self,
        context: ConfirmationContext,
        *,
        reason: ReasonType,
        explanation: str,
    ) -> Verdict:
        return Verdict(
            decision=Decision.FORBIDDEN if reason == ReasonType.USER_REJECTED
            else Decision.UNDECIDABLE,
            reason_type=reason,
            justification_chain=(
                f"User-Confirmation-Loop: {explanation}",
            ),
            action_type=context.proposed_action_type,
            agent_id=context.principal or "",
        )

    def _audit_lifecycle(
        self,
        context: ConfirmationContext,
        view: ConfirmationView,
        *,
        decision: ConfirmationDecision | None,
        outcome: GateOutcome,
    ) -> None:
        if self._audit is None:
            return
        import contextlib

        # Audit must never break the gate path. Swallow — the underlying
        # AuditTrail already logs internally.
        with contextlib.suppress(Exception):
            self._audit.log_confirmation(
                trigger_reasons=sorted(t.value for t in context.triggers),
                echo_format=view.echo_format.value,
                principal=decision.principal if decision else "",
                proposed_action_type=context.proposed_action_type,
                user_intent=context.user_intent,
                confirmed=decision.confirmed if decision else False,
                response_time_ms=decision.response_time_ms if decision else 0,
                final_decision=outcome.value,
            )
