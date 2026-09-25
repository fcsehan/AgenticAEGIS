"""AEGIS-2714 (Epic 27) — Plan-soundness theorems Pl-Sound-1..7.

Formal soundness properties verified via constructive scenarios:

- Pl-Sound-1: PERMITTED ⇒ ∀ s. per-step decision == PERMITTED.
- Pl-Sound-2: constraint violated ⇒ violations carries the
  constraint_id reference.
- Pl-Sound-3: blocking violation ⇒ FORBIDDEN, never PERMITTED.
- Pl-Sound-4: obligateSequence A B violated ⇒ FORBIDDEN.
- Pl-Sound-5: forbidAggregate A k, count(A) > k ⇒ FORBIDDEN.
- Pl-Sound-6: obligateWithin A N, cumulative duration > N ⇒ FORBIDDEN.
- Pl-Sound-7: requirePrecondition A φ, φ does not hold ⇒ FORBIDDEN.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.plan import (
    Plan,
    PlanStep,
    StateSnapshot,
    ViolationType,
)
from aegis.guard.verdict import Decision, PlanDecision

DEVOPS = Path("aegis/domains/devops")


@pytest.fixture(scope="module")
def guard() -> Guard:
    return Guard.from_meld_files([
        DEVOPS / "DevOpsDomainOntologyMt.meld",
        DEVOPS / "DevOpsActionVocabMt.meld",
        DEVOPS / "DevOpsDeonticRulesMt.meld",
        DEVOPS / "DevOpsPlanNormsMt.meld",
    ])


def _step(action_type: str, agent: str = "ciAgent",
          duration: float = 0.0,
          pre: dict | None = None,
          post: dict | None = None) -> PlanStep:
    return PlanStep(
        action=Action(action_type=action_type, agent_id=agent),
        scheduled_duration_s=duration,
        pre_state=StateSnapshot(fields=pre or {}),
        post_state=StateSnapshot(fields=post or {}),
    )


# ── Pl-Sound-1: PERMITTED ⇒ all steps PERMITTED ───────────────────


class TestSound1AllStepsPermittedWhenPlanPermitted:
    def _scenarios(self) -> list[Plan]:
        return [
            Plan(steps=(_step("buildArtifact",
                              post={"buildStatus": "success"}),
                        _step("testArtifact",
                              post={"testStatus": "passed"}),
                        _step("deployArtifact"))),
            Plan(steps=(_step("emergencyRollback"),)),
            Plan(steps=(_step("requestApproval"),)),
        ]

    @pytest.mark.parametrize("plan_index", [0, 1, 2])
    def test_each_permitted_plan_has_permitted_steps(
        self, guard: Guard, plan_index: int,
    ) -> None:
        plan = self._scenarios()[plan_index]
        verdict = guard.plan_check(plan)
        if verdict.plan_decision == PlanDecision.PERMITTED:
            for step_v in verdict.per_step_verdicts:
                assert step_v.decision == Decision.PERMITTED


# ── Pl-Sound-2: constraint violated ⇒ violations carries ref ─────


class TestSound2ViolationCarriesConstraintRef:
    def test_sequence_violation_has_constraint_id(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("deployArtifact"), _step("testArtifact"),
        ))
        verdict = guard.plan_check(plan)
        seq = [v for v in verdict.violations
               if v.violation_type == ViolationType.SEQUENCE_VIOLATION]
        assert seq
        assert all(v.constraint_id for v in seq)

    def test_aggregate_violation_has_constraint_id(self, guard: Guard) -> None:
        plan = Plan(steps=tuple(
            _step("buildArtifact", post={"buildStatus": "success"}) if i == 0
            else _step("testArtifact", post={"testStatus": "passed"}) if i == 1
            else _step("deployArtifact")
            for i in range(6)
        ))
        verdict = guard.plan_check(plan)
        agg = [v for v in verdict.violations
               if v.violation_type == ViolationType.AGGREGATE_VIOLATION]
        assert agg
        assert all(v.constraint_id for v in agg)

    def test_precondition_violation_has_constraint_id(
        self, guard: Guard,
    ) -> None:
        plan = Plan(steps=(
            _step("buildArtifact"),
            _step("testArtifact", post={"testStatus": "failed"}),
            _step("deployArtifact"),
        ))
        verdict = guard.plan_check(plan)
        pre = [v for v in verdict.violations
               if v.violation_type == ViolationType.PRECONDITION_VIOLATION]
        assert pre
        assert all(v.constraint_id for v in pre)


# ── Pl-Sound-3: blocking violation ⇒ FORBIDDEN ────────────────────


class TestSound3BlockingNeverPermitted:
    @pytest.mark.parametrize("plan_factory_idx", [0, 1, 2, 3])
    def test_blocking_plans_never_permitted(
        self, guard: Guard, plan_factory_idx: int,
    ) -> None:
        plans = [
            Plan(steps=(_step("deployArtifact"), _step("testArtifact"))),
            Plan(steps=(_step("forceModifyRepository"),)),
            Plan(steps=tuple(_step("deployArtifact") for _ in range(5))),
            Plan(steps=(_step("buildArtifact"),
                        _step("testArtifact",
                              post={"testStatus": "failed"}),
                        _step("deployArtifact"))),
        ]
        verdict = guard.plan_check(plans[plan_factory_idx])
        assert verdict.plan_decision != PlanDecision.PERMITTED


# ── Pl-Sound-4: obligateSequence violation ⇒ FORBIDDEN ─────────────


class TestSound4SequenceViolationBlocks:
    def test_inverse_order_blocked(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("deployArtifact"),
            _step("testArtifact"),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN

    def test_intermediate_step_does_not_save(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("deployArtifact"),
            _step("requestApproval"),
            _step("testArtifact"),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN

    def test_correct_order_with_extra_step_passes(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", post={"buildStatus": "success"}),
            _step("requestApproval"),
            _step("testArtifact", post={"testStatus": "passed"}),
            _step("deployArtifact"),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED


# ── Pl-Sound-5: forbidAggregate count > k ⇒ FORBIDDEN ─────────────


class TestSound5AggregateOverThresholdBlocks:
    def test_over_threshold_three_deploys_passes(self, guard: Guard) -> None:
        # Threshold for deployArtifact is 3 — three deploys is exactly
        # the limit, not over.
        plan = Plan(steps=(
            _step("buildArtifact", post={"buildStatus": "success"}),
            _step("testArtifact", post={"testStatus": "passed"}),
            _step("deployArtifact"),
            _step("deployArtifact"),
            _step("deployArtifact"),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED

    def test_over_threshold_four_deploys_blocked(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", post={"buildStatus": "success"}),
            _step("testArtifact", post={"testStatus": "passed"}),
            _step("deployArtifact"),
            _step("deployArtifact"),
            _step("deployArtifact"),
            _step("deployArtifact"),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN

    def test_threshold_zero_any_occurrence_blocks(self, guard: Guard) -> None:
        # forceModifyRepository has threshold 0.
        plan = Plan(steps=(_step("forceModifyRepository"),))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN


# ── Pl-Sound-6: obligateWithin cumulative > N ⇒ FORBIDDEN ─────────


class TestSound6WithinDurationBlocks:
    def test_under_budget_passes(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", duration=300.0,
                  post={"buildStatus": "success"}),
            _step("testArtifact", duration=300.0,
                  post={"testStatus": "passed"}),
            _step("deployArtifact"),  # cumulative before = 600 ≤ 1800.
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED

    def test_over_budget_blocked(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", duration=1000.0,
                  post={"buildStatus": "success"}),
            _step("testArtifact", duration=900.0,
                  post={"testStatus": "passed"}),
            _step("deployArtifact"),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN

    def test_immediate_at_index_zero_passes(self, guard: Guard) -> None:
        plan = Plan(steps=(_step("emergencyRollback"),))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED

    def test_immediate_not_at_index_zero_blocks(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", post={"buildStatus": "success"}),
            _step("emergencyRollback"),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN


# ── Pl-Sound-7: requirePrecondition φ false ⇒ FORBIDDEN ───────────


class TestSound7PreconditionFailureBlocks:
    def test_missing_precondition_blocks(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", post={"buildStatus": "success"}),
            _step("testArtifact"),  # no testStatus posted.
            _step("deployArtifact"),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN

    def test_wrong_value_blocks(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", post={"buildStatus": "success"}),
            _step("testArtifact", post={"testStatus": "skipped"}),
            _step("deployArtifact"),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN

    def test_satisfied_passes(self, guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", post={"buildStatus": "success"}),
            _step("testArtifact", post={"testStatus": "passed"}),
            _step("deployArtifact"),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED
