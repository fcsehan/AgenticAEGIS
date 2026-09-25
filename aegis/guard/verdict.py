"""Verdict — the output of Guard.check().

Every Guard.check() call returns a Verdict: PERMITTED, FORBIDDEN, or UNDECIDABLE,
always with a justification chain for audit (I3).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(Enum):
    """The three-valued Guard decision per D-001."""

    PERMITTED = "PERMITTED"
    FORBIDDEN = "FORBIDDEN"
    UNDECIDABLE = "UNDECIDABLE"


class ReasonType(Enum):
    """Machine-readable reason classification per D-001/D-004."""

    EXPLICIT_NORM = "EXPLICIT_NORM"
    """A concrete norm was applied."""

    CWA_NO_PERMISSION = "CWA_NO_PERMISSION"
    """CWA: No permission found in the domain."""

    NO_JURISDICTION = "NO_JURISDICTION"
    """No loaded domain covers this action type."""

    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"
    """Conflicting norms could not be resolved."""

    INTERNAL_ERROR = "INTERNAL_ERROR"
    """Engine exception during evaluation (D-004)."""

    EVALUATION_TIMEOUT = "EVALUATION_TIMEOUT"
    """Evaluation exceeded time limit (D-007)."""

    INVALID_ACTION = "INVALID_ACTION"
    """Action failed input validation (D-007)."""

    MISSING_CONTEXT = "MISSING_CONTEXT"
    """Required context field is missing (D-010)."""

    MORAL_AXIOM = "MORAL_AXIOM"
    """Non-defeasible moral axiom applied."""

    NO_CANDIDATES = "NO_CANDIDATES"
    """check_candidates was called with an empty list (Epic 32, AEGIS-3203)."""

    ALL_CANDIDATES_FORBIDDEN = "ALL_CANDIDATES_FORBIDDEN"
    """Every candidate action received FORBIDDEN (Epic 32, AEGIS-3203)."""

    MULTIPLE_MINIMAL_CANDIDATES = "MULTIPLE_MINIMAL_CANDIDATES"
    """Several incomparable narrowest PERMITTED candidates; deterministic
    tie-break selected one but the set is logged for audit (Epic 32,
    AEGIS-3203)."""

    USER_REJECTED = "USER_REJECTED"
    """User-Confirmation-Loop: the human oracle declined the proposed
    action (Epic 33, AEGIS-3302)."""

    CONFIRMATION_TIMEOUT = "CONFIRMATION_TIMEOUT"
    """User-Confirmation-Loop: the user did not respond within the
    configured timeout window (Epic 33, AEGIS-3301)."""

    CONFIRMATION_PRINCIPAL_UNAUTHORIZED = "CONFIRMATION_PRINCIPAL_UNAUTHORIZED"
    """User-Confirmation-Loop: a principal answered who is not on the
    policy's authorized list (Epic 33, AEGIS-3304)."""


@dataclass(frozen=True, slots=True)
class Verdict:
    """The result of a Guard.check() call.

    Attributes:
        decision: The three-valued outcome.
        reason_type: Machine-readable classification.
        justification_chain: Ordered reasoning steps for audit.
        norms_applied: IDs/sources of norms that contributed.
        action_type: The action type that was checked.
        agent_id: The agent that proposed the action.
        permit_token_id: Issued permit token (PERMITTED only, AEGIS-1504).
        evaluation_mode: Identifier for the resolution strategy that
            produced this verdict — ``"ddic"`` (v2 forward-chaining),
            ``"legacy"`` (v1 6-step on a compiled module), or
            ``"v1_legacy"`` (direct DDICEngine fallback). Auditors and
            release-gate tooling rely on this to verify that production
            domains run on the formal DDIC path. Required by AEGIS-2309
            acceptance criterion #4.
    """

    decision: Decision
    reason_type: ReasonType
    justification_chain: tuple[str, ...] = ()
    norms_applied: tuple[str, ...] = ()
    action_type: str = ""
    agent_id: str = ""
    permit_token_id: str = ""
    evaluation_mode: str = ""

    def explain(self) -> str:
        """Human-readable explanation."""
        lines = [
            f"Decision: {self.decision.value}",
            f"Reason: {self.reason_type.value}",
        ]
        if self.norms_applied:
            lines.append("Norms applied:")
            for norm in self.norms_applied:
                lines.append(f"  - {norm}")
        if self.justification_chain:
            lines.append("Justification:")
            for step in self.justification_chain:
                lines.append(f"  {step}")
        return "\n".join(lines)

    def explain_safe(self) -> str:
        """Safe explanation without norm names or internal details."""
        return f"Decision: {self.decision.value}\nReason: {self.reason_type.value}"


class PlanDecision(Enum):
    """Plan-level decision (AEGIS-2702, Epic 27).

    Mirrors ``Decision`` but applies to a whole plan rather than a
    single action. The semantics are conservative:

    - ``PERMITTED``: every step's verdict is PERMITTED *and* every
      plan-level constraint holds.
    - ``FORBIDDEN``: at least one violation exists with severity
      ``critical`` (e.g. a forbidden aggregate, a missed obligation
      under coverage-required mode).
    - ``UNDECIDABLE``: the evaluator cannot certify the plan
      (e.g. a step verdict is UNDECIDABLE; or the stub returns this
      until the real evaluator lands in AEGIS-2710).
    """

    PERMITTED = "PERMITTED"
    FORBIDDEN = "FORBIDDEN"
    UNDECIDABLE = "UNDECIDABLE"


@dataclass(frozen=True, slots=True)
class PlanVerdict:
    """Result of ``Guard.plan_check`` (AEGIS-2702, Epic 27).

    Carries:
    - ``plan_decision``: the three-valued plan outcome.
    - ``per_step_verdicts``: tuple of ``Verdict`` instances, one per
      step in the input plan, preserved for audit.
    - ``violations``: tuple of plan-level constraint violations.
    - ``reason_summary``: short machine-readable code for the
      blocking reason (or ``""`` when permitted / undecidable).
    """

    plan_decision: PlanDecision
    per_step_verdicts: tuple[Verdict, ...] = ()
    violations: tuple[object, ...] = ()
    reason_summary: str = ""
    evaluation_mode: str = ""


@dataclass(frozen=True, slots=True)
class CandidateVerdict:
    """Result of ``Guard.check_candidates`` (Epic 32, AEGIS-3203).

    Bundles the chosen Verdict together with the per-candidate evaluation
    so an auditor can see *why* one candidate was preferred over another.
    Backward compatibility with ``Guard.check`` is preserved by
    construction: ``check_candidates([action]).chosen`` is structurally
    identical to ``check(action)``.

    Attributes:
        chosen: The Verdict that the caller should act on. Always
            present, even when no candidate was PERMITTED — in that
            case it carries the consolidated FORBIDDEN/UNDECIDABLE
            decision.
        per_candidate: Tuple of (action_type, Verdict) for every input
            action, in input order. Empty when the input list was empty.
        minimal_candidates: Action types that emerged as narrowest
            PERMITTED candidates before tie-break. Empty when no
            candidate was PERMITTED. A length > 1 indicates that the
            domain has incomparable narrowest actions and that the
            tie-break rule (deterministic lex sort) decided.
    """

    chosen: Verdict
    per_candidate: tuple[tuple[str, Verdict], ...] = ()
    minimal_candidates: tuple[str, ...] = ()
