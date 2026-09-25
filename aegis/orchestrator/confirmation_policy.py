"""User-Confirmation-Loop policy data model (AEGIS-3301, Epic 33).

Captures the four engineering decisions that turn a "click-to-confirm"
dialog into a real risk-reduction control:

1. **When** must we ask? (``triggers``)
2. **Who** is allowed to answer? (``authorized_principals``)
3. **What** do we do if no one answers in time? (``timeout_seconds`` +
   ``timeout_action``)
4. **How** do we ask, so the answer is meaningful? (``echo_format``)

The policy is configured per domain. Defaults for the six bundled
domains live in AEGIS-3305 (separate file). This module only defines
the data model and the trigger-evaluation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TriggerCondition(Enum):
    """Condition under which a User-Confirmation-Loop is required.

    Each enum value corresponds to a concrete signal observable in the
    orchestrator pipeline.
    """

    MULTIPLE_MINIMAL_CANDIDATES = "MULTIPLE_MINIMAL_CANDIDATES"
    """Epic 32: ``Guard.check_candidates`` reported >1 incomparable
    minimal PERMITTED candidates and used a deterministic tie-break."""

    VALIDATOR_DRIFT = "VALIDATOR_DRIFT"
    """Epic 31 (deferred): the Intent-Action-Validator reported drift
    between the declared intent and the chosen action."""

    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    """Epic 31 (deferred): the validator's confidence score is below
    the configured threshold."""

    ACTION_SUBSTITUTION_DRIFT = "ACTION_SUBSTITUTION_DRIFT"
    """Epic 34: a red-team-style detector flagged a drift mid-conversation."""


class TimeoutAction(Enum):
    """What happens when the user does not respond within ``timeout_seconds``."""

    FAIL_CLOSED = "FAIL_CLOSED"
    """The verdict becomes ``UNDECIDABLE`` with reason
    ``CONFIRMATION_TIMEOUT``. Default for high-risk domains."""

    ESCALATE_TO_REVIEWER = "ESCALATE_TO_REVIEWER"
    """Forwards the confirmation request to a configured reviewer.
    The action is paused until the reviewer answers; if the reviewer
    also times out, the verdict falls back to FAIL_CLOSED."""


class EchoFormat(Enum):
    """How the confirmation prompt is presented to the user.

    The format choice has a direct anti-consent-theater intent:
    ACTIVE_RESTATE forces the user to engage; PASSIVE_YES_NO is a
    single-click acknowledgement; EXPLICIT_SELECT works when the
    confirmation is "which of these candidates did you mean?".
    """

    PASSIVE_YES_NO = "PASSIVE_YES_NO"
    """Single Yes/No button. Lowest friction, highest theater risk."""

    ACTIVE_RESTATE = "ACTIVE_RESTATE"
    """The user must restate the action in their own words. The
    confirmation_renderer (AEGIS-3303) checks word-overlap with the
    declared ``actionDescription``."""

    EXPLICIT_SELECT = "EXPLICIT_SELECT"
    """The user picks one of N enumerated candidates. Fits naturally
    when the trigger is ``MULTIPLE_MINIMAL_CANDIDATES``."""


@dataclass(frozen=True, slots=True)
class ConfirmationPolicy:
    """Per-domain User-Confirmation-Loop policy.

    Attributes:
        triggers: conditions under which a confirmation is required.
            Empty tuple = the policy never fires (effectively disabled).
        authorized_principals: roles that may confirm. Empty tuple =
            "any authenticated principal" (only safe in single-user
            CLI contexts).
        timeout_seconds: how long to wait for a response.
        timeout_action: behaviour on timeout.
        echo_format: how the prompt is rendered to the user.
        domain: identifier of the domain this policy belongs to. Free
            text; used only in audit records.
    """

    triggers: tuple[TriggerCondition, ...] = ()
    authorized_principals: tuple[str, ...] = ()
    timeout_seconds: int = 60
    timeout_action: TimeoutAction = TimeoutAction.FAIL_CLOSED
    echo_format: EchoFormat = EchoFormat.PASSIVE_YES_NO
    domain: str = ""

    def should_confirm(self, signals: frozenset[TriggerCondition]) -> bool:
        """Return True if any of ``signals`` matches a configured
        trigger.

        ``signals`` is a snapshot of the pipeline's current trigger
        state, gathered by the orchestrator after the validator and
        ``check_candidates`` steps. The check is set-membership;
        priority among triggers is not modelled because all triggers
        produce the same response (ask the user).
        """
        if not self.triggers:
            return False
        return bool(signals & frozenset(self.triggers))

    def is_authorized(self, principal: str) -> bool:
        """Return True if ``principal`` may answer this policy's
        confirmation prompt.

        Empty ``authorized_principals`` is intentionally permissive
        (any principal allowed) — that's a useful default for
        single-user dev/test setups but should be tightened in
        production via AEGIS-3304 + AEGIS-3305.
        """
        if not self.authorized_principals:
            return True
        return principal in self.authorized_principals


@dataclass(frozen=True, slots=True)
class ConfirmationDecision:
    """The user's (or reviewer's) response to a confirmation prompt."""

    confirmed: bool
    response_text: str = ""  # populated for ACTIVE_RESTATE
    selected_action_type: str = ""  # populated for EXPLICIT_SELECT
    response_time_ms: int = 0
    principal: str = ""


@dataclass(frozen=True, slots=True)
class ConfirmationContext:
    """Snapshot of the orchestrator state when a confirmation triggers.

    Bundled here so trigger evaluation, view rendering (AEGIS-3303),
    authorization check (AEGIS-3304) and audit logging (AEGIS-3306)
    all see exactly the same view of the world.
    """

    user_intent: str
    proposed_action_type: str
    proposed_action_description: str
    minimal_candidates: tuple[str, ...] = ()
    validator_drift_reason: str = ""
    confidence: float | None = None
    triggers: frozenset[TriggerCondition] = field(default_factory=frozenset)
    principal: str = ""
