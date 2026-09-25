"""AEGIS-2710 (Epic 27) — PlanPipeline.

Guard-side adapter that turns a ``Plan`` into a ``PlanVerdict`` by
combining:

1. Per-step delegation through ``Guard.check`` so every step inherits
   the existing CWA / MISSING_CONTEXT / INVALID_ACTION semantics — the
   "backward-compat by construction" property is enforced by an
   equivalence test (``Guard.plan_check(Plan.from_action(a)).
   per_step_verdicts[0].decision == Guard.check(a).decision``).

2. Plan-level analysis through the Core ``evaluate_plan_module`` for
   sequence/aggregate/timing/precondition violations and obligation
   coverage.

3. A small aggregation table that maps the per-step verdicts plus the
   plan-level violations onto the three ``PlanDecision`` outcomes.

Stages: validate (D-007 limits) → enrich (per step) → per_step_eval
(via Guard.check) → plan_constraint_check (via Core) → aggregate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aegis.engine.plan_eval import (
    PlanCoreOutcome,
    PlanCoreViolation,
    PlanCoreViolationKind,
    PlanStepView,
    PlanView,
    evaluate_plan_module,
)
from aegis.guard.plan import (
    ObligationCoverage,
    ObligationMatch,
    Plan,
    PlanViolation,
    ViolationType,
)
from aegis.guard.verdict import (
    Decision,
    PlanDecision,
    PlanVerdict,
    ReasonType,
    Verdict,
)

if TYPE_CHECKING:
    from aegis.guard.guard import Guard


# Map Core violation kinds to Guard violation types. Identical string
# values across the boundary make the mapping a one-liner.
_CORE_KIND_TO_VIOLATION_TYPE: dict[PlanCoreViolationKind, ViolationType] = {
    PlanCoreViolationKind.SEQUENCE: ViolationType.SEQUENCE_VIOLATION,
    PlanCoreViolationKind.AGGREGATE: ViolationType.AGGREGATE_VIOLATION,
    PlanCoreViolationKind.TIMING: ViolationType.TIMING_VIOLATION,
    PlanCoreViolationKind.PRECONDITION: ViolationType.PRECONDITION_VIOLATION,
    PlanCoreViolationKind.STEP_FORBIDDEN: ViolationType.STEP_FORBIDDEN,
    PlanCoreViolationKind.STEP_UNDECIDABLE: ViolationType.STEP_UNDECIDABLE,
    PlanCoreViolationKind.OBLIGATION_UNCOVERED: ViolationType.OBLIGATION_UNCOVERED,
    PlanCoreViolationKind.EMPTY_PLAN: ViolationType.EMPTY_PLAN,
}


class PlanPipeline:
    """Pipeline that turns a ``Plan`` into a ``PlanVerdict``.

    Owned by the Guard; receives a back-reference so the per-step
    delegation calls ``Guard.check`` directly. That single decision
    is what guarantees the AEGIS-2710 acceptance #2 (equivalence by
    construction): a 1-step plan returns the same per-step decision
    as the action API would on its own.
    """

    def __init__(self, guard: Guard) -> None:
        self._guard = guard

    def run(self, plan: Plan) -> PlanVerdict:
        """Evaluate ``plan`` and return a ``PlanVerdict``.

        Stages:

        1. ``validate``: D-007 plan-level limits (step count, state
           field counts, byte budget). Limit violation → UNDECIDABLE
           with ``reason_summary="d_007_limit"``.
        2. Empty plan → FORBIDDEN with ``reason_summary="empty_plan"``.
        3. ``per_step_eval``: ``Guard.check`` per step; the existing
           pipeline applies enrichers, validates context, and
           computes the per-step ``Verdict``. The full ordered tuple
           is preserved on the result for audit.
        4. ``plan_constraint_check``: Core ``evaluate_plan_module``
           runs sequence/aggregate/timing/precondition + obligation
           coverage on a ``PlanView`` projection of the plan.
        5. ``aggregate``: rule table maps per-step decisions and
           plan-level violations onto ``PlanDecision``.
        """
        # Stage 1: D-007 validate.
        limit_issues = plan.validate_limits()
        if limit_issues:
            return _undecidable_plan(
                "d_007_limit",
                evaluation_mode=self._evaluation_mode(),
            )

        # Stage 2: empty plan rejection.
        if not plan.steps:
            return PlanVerdict(
                plan_decision=PlanDecision.FORBIDDEN,
                per_step_verdicts=(),
                violations=(PlanViolation(
                    violation_type=ViolationType.EMPTY_PLAN,
                    detail="empty_plan",
                ),),
                reason_summary="empty_plan",
                evaluation_mode=self._evaluation_mode(),
            )

        # Stage 3: per-step evaluation via Guard.check.
        per_step_verdicts: tuple[Verdict, ...] = tuple(
            self._guard.check(step.action) for step in plan.steps
        )

        # Stage 4: Core plan-level analysis.
        plan_view = _plan_to_view(plan)
        if self._guard._module is None:
            # No compiled module available — Core can't run. Surface
            # this as UNDECIDABLE rather than silently ignoring
            # plan-level constraints.
            return _undecidable_plan(
                "module_not_available",
                evaluation_mode=self._evaluation_mode(),
                per_step=per_step_verdicts,
            )
        core_result = evaluate_plan_module(
            self._guard._module,
            plan_view,
            self._guard._inheritance,
        )

        # Stage 5: aggregate.
        guard_violations = _translate_violations(core_result.plan_violations_core)
        plan_decision = _aggregate_plan_decision(
            per_step_verdicts, core_result, guard_violations
        )
        reason = _build_reason_summary(
            plan_decision, per_step_verdicts, core_result, guard_violations
        )
        return PlanVerdict(
            plan_decision=plan_decision,
            per_step_verdicts=per_step_verdicts,
            violations=guard_violations,
            reason_summary=reason,
            evaluation_mode=self._evaluation_mode(),
        )

    def coverage(self, plan: Plan) -> ObligationCoverage:
        """Return obligation coverage for ``plan`` without running
        per-step Guard.check. Useful for tooling and tests that only
        need the coverage report."""
        if self._guard._module is None or not plan.steps:
            return ObligationCoverage()
        plan_view = _plan_to_view(plan)
        core_result = evaluate_plan_module(
            self._guard._module,
            plan_view,
            self._guard._inheritance,
        )
        cov = core_result.obligation_coverage
        return ObligationCoverage(
            matches=tuple(
                ObligationMatch(
                    obligation_id=m.formula_id,
                    matched_step_index=m.matched_step_index,
                    matched_action_type=m.matched_action_type,
                )
                for m in cov.satisfied
            ),
            uncovered_obligation_ids=tuple(u.formula_id for u in cov.unsatisfied),
        )

    def _evaluation_mode(self) -> str:
        module = self._guard._module
        if module is None:
            return "v1_legacy"
        if module.resolution_strategy == "legacy":
            return "legacy"
        return "ddic"


# ── Helpers ────────────────────────────────────────────────────────


def _plan_to_view(plan: Plan) -> PlanView:
    """Project a Guard ``Plan`` into a Core ``PlanView``."""
    steps = tuple(
        PlanStepView(
            step_index=index,
            action_type=step.action.action_type,
            agent=step.action.agent_id,
            proposition=_action_to_proposition(step.action),
            scheduled_duration_s=step.scheduled_duration_s,
            pre_state_fields=dict(step.pre_state.fields),
            post_state_fields=dict(step.post_state.fields),
        )
        for index, step in enumerate(plan.steps)
    )
    return PlanView(
        steps=steps,
        initial_state_fields=dict(plan.initial_state.fields),
        plan_id=plan.plan_id,
    )


def _action_to_proposition(action: object) -> tuple[object, ...]:
    """Mirror of ``EvaluationPipeline._to_proposition`` but local so
    PlanPipeline doesn't import the whole pipeline module just for
    one helper. The signature here is deliberately ``object`` — the
    Action type carries the relevant fields and PlanStep has already
    handed us one."""
    action_type = getattr(action, "action_type", "")
    proposition = getattr(action, "proposition", None) or {}
    if not proposition:
        return (action_type,)
    head = action_type
    args = []
    for key in sorted(proposition.keys()):
        args.append(proposition[key])
    return (head, *args)


def _translate_violations(
    core_violations: tuple[PlanCoreViolation, ...],
) -> tuple[PlanViolation, ...]:
    """Map Core violations into Guard PlanViolations.

    Skipped on purpose:
    - ``PLAN_TOO_LONG``: converted to a top-level UNDECIDABLE upstream.
    - ``STEP_FORBIDDEN`` / ``STEP_UNDECIDABLE``: these are
      reflections of the per-step Verdict and would double-count.
      The Guard already carries them via ``per_step_verdicts``;
      duplicating them here would also incorrectly flip an
      UNDECIDABLE plan to FORBIDDEN through the
      ``has_blocking_violation`` aggregation rule.
    """
    duplicative_kinds = {
        PlanCoreViolationKind.PLAN_TOO_LONG,
        PlanCoreViolationKind.STEP_FORBIDDEN,
        PlanCoreViolationKind.STEP_UNDECIDABLE,
    }
    out: list[PlanViolation] = []
    for v in core_violations:
        if v.kind in duplicative_kinds:
            continue
        guard_kind = _CORE_KIND_TO_VIOLATION_TYPE.get(v.kind)
        if guard_kind is None:
            continue
        out.append(
            PlanViolation(
                violation_type=guard_kind,
                step_index=v.step_index,
                constraint_id=v.constraint_id,
                detail=v.detail,
            )
        )
    return tuple(out)


def _aggregate_plan_decision(
    per_step_verdicts: tuple[Verdict, ...],
    core_result: object,
    plan_violations: tuple[PlanViolation, ...],
) -> PlanDecision:
    """Apply the AEGIS-2710 aggregation table.

    Rules (in order):
    1. Any FORBIDDEN per-step verdict → BLOCKED.
    2. Any blocking plan-level violation → BLOCKED. (fail-closed)
    3. Any UNDECIDABLE per-step verdict → UNDECIDABLE.
    4. Otherwise EXECUTABLE → PERMITTED.

    Note that #2 takes priority over #3: an UNDECIDABLE step alongside
    a blocking violation is BLOCKED (fail-closed), per the AEGIS-2710
    acceptance "UNDECIDABLE + blocking Violation → BLOCKED".
    """
    # Core's PLAN_TOO_LONG path arrives here as overall UNDECIDABLE
    # without a Guard-side blocking violation. Honour it.
    overall = getattr(core_result, "overall_outcome", PlanCoreOutcome.EXECUTABLE)

    has_forbidden = any(
        v.decision == Decision.FORBIDDEN for v in per_step_verdicts
    )
    has_undecidable = any(
        v.decision == Decision.UNDECIDABLE for v in per_step_verdicts
    )
    has_blocking_violation = bool(plan_violations)

    if has_forbidden:
        return PlanDecision.FORBIDDEN
    if has_blocking_violation:
        return PlanDecision.FORBIDDEN
    if has_undecidable or overall == PlanCoreOutcome.UNDECIDABLE:
        return PlanDecision.UNDECIDABLE
    return PlanDecision.PERMITTED


def _build_reason_summary(
    plan_decision: PlanDecision,
    per_step_verdicts: tuple[Verdict, ...],
    core_result: object,
    plan_violations: tuple[PlanViolation, ...],
) -> str:
    if plan_decision == PlanDecision.PERMITTED:
        return ""
    # Forbidden: prefer the first FORBIDDEN per-step reason; else the
    # first plan-level violation kind.
    if plan_decision == PlanDecision.FORBIDDEN:
        for v in per_step_verdicts:
            if v.decision == Decision.FORBIDDEN:
                return f"step_forbidden:{v.action_type}"
        if plan_violations:
            return plan_violations[0].violation_type.value.lower()
        return "blocked"
    # UNDECIDABLE: report the originating reason from Core if any,
    # else the first UNDECIDABLE per-step reason_type.
    summary = getattr(core_result, "reason_summary", "")
    if summary:
        return summary
    for v in per_step_verdicts:
        if v.decision == Decision.UNDECIDABLE:
            return f"step_undecidable:{v.reason_type.value}"
    return "undecidable"


def _undecidable_plan(
    reason: str,
    evaluation_mode: str,
    per_step: tuple[Verdict, ...] = (),
) -> PlanVerdict:
    """Build a top-level UNDECIDABLE PlanVerdict for limit / module
    failures. No constraint violations are attached because these
    cases short-circuit before plan-constraint analysis runs."""
    placeholder = Verdict(
        decision=Decision.UNDECIDABLE,
        reason_type=ReasonType.INVALID_ACTION,
    )
    if not per_step:
        per_step = (placeholder,)
    return PlanVerdict(
        plan_decision=PlanDecision.UNDECIDABLE,
        per_step_verdicts=per_step,
        violations=(),
        reason_summary=reason,
        evaluation_mode=evaluation_mode,
    )


__all__ = [
    "PlanPipeline",
]
