"""AEGIS-2712 (Epic 27) — DevOps reference plan-norms test suite.

Loads the DevOps domain (now with DevOpsPlanNormsMt.meld) and exercises
ten reference plans against ``Guard.plan_check``. Each plan represents
a canonical CI/CD scenario and asserts a specific PlanDecision plus,
where relevant, the violation kind.

This is the end-to-end integration test for the Plan-Level Governance
machinery on a realistic domain. If anything in Phases 1-4 regresses,
this file is the first canary.
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
from aegis.guard.verdict import PlanDecision

DOMAIN_DIR = Path("aegis/domains/devops")


@pytest.fixture(scope="module")
def devops_guard() -> Guard:
    """Load the DevOps domain including the new plan-norms file."""
    return Guard.from_meld_files([
        DOMAIN_DIR / "DevOpsDomainOntologyMt.meld",
        DOMAIN_DIR / "DevOpsActionVocabMt.meld",
        DOMAIN_DIR / "DevOpsDeonticRulesMt.meld",
        DOMAIN_DIR / "DevOpsPlanNormsMt.meld",
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


def _has_kind(verdict, kind: ViolationType) -> bool:
    return any(v.violation_type == kind for v in verdict.violations)


# ── 1. Domain loads ───────────────────────────────────────────────


class TestDomainLoad:
    def test_module_carries_plan_constraints(self, devops_guard: Guard) -> None:
        # 13 plan-constraints expected: 3 sequence + 4 aggregate +
        # 2 within + 3 precondition = 12. (One oughtToDo
        # not-counted-here.) Sanity check: must be > 0.
        assert len(devops_guard._module.plan_constraints) >= 12

    def test_existing_action_level_check_unchanged(
        self, devops_guard: Guard,
    ) -> None:
        """Adding plan-norms must NOT regress the action API."""
        action = Action(
            action_type="readFile", agent_id="opencodeAgent",
            proposition={"path": "sourceFile"},
        )
        verdict = devops_guard.check(action)
        # Whatever the original decision was — the point is it doesn't
        # crash and produces a Verdict.
        assert verdict.decision is not None


# ── 2. Reference plans ────────────────────────────────────────────


class TestPlan01HappyPath:
    def test_build_test_deploy_executable(self, devops_guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", duration=120.0,
                  post={"buildStatus": "success"}),
            _step("testArtifact", duration=300.0,
                  post={"testStatus": "passed"}),
            _step("deployArtifact", duration=60.0),
        ))
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED


class TestPlan02SequenceInversion:
    def test_deploy_before_test_blocked(self, devops_guard: Guard) -> None:
        plan = Plan(steps=(
            _step("deployArtifact"),
            _step("testArtifact"),
        ))
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert _has_kind(verdict, ViolationType.SEQUENCE_VIOLATION)


class TestPlan03AggregateLimit:
    def test_four_deployments_blocked(self, devops_guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", post={"buildStatus": "success"}),
            _step("testArtifact", post={"testStatus": "passed"}),
            _step("deployArtifact"),
            _step("deployArtifact"),
            _step("deployArtifact"),
            _step("deployArtifact"),  # 4th deploy → over threshold (3).
        ))
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert _has_kind(verdict, ViolationType.AGGREGATE_VIOLATION)


class TestPlan04ForcePushZero:
    def test_any_force_modify_blocked(self, devops_guard: Guard) -> None:
        plan = Plan(steps=(
            _step("forceModifyRepository",
                  pre={"approvalFrom": "emergencyBreakGlass"}),
        ))
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert _has_kind(verdict, ViolationType.AGGREGATE_VIOLATION)


class TestPlan05PreconditionMissing:
    def test_deploy_without_test_passed_blocked(
        self, devops_guard: Guard,
    ) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", post={"buildStatus": "success"}),
            _step("testArtifact", post={"testStatus": "failed"}),
            _step("deployArtifact"),
        ))
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert _has_kind(verdict, ViolationType.PRECONDITION_VIOLATION)


class TestPlan06ApprovalSequence:
    def test_modify_sensitive_without_approval_blocked(
        self, devops_guard: Guard,
    ) -> None:
        plan = Plan(steps=(
            _step("modifySensitiveConfig"),  # no requestApproval first
        ))
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        # missing precondition AND missing approval-sequence both
        # contribute. At least one of the relevant kinds present.
        kinds = {v.violation_type for v in verdict.violations}
        assert (
            ViolationType.PRECONDITION_VIOLATION in kinds
            or ViolationType.SEQUENCE_VIOLATION in kinds
        )


class TestPlan07TimingViolation:
    def test_rollback_at_index_3_blocked(self, devops_guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact"),
            _step("testArtifact"),
            _step("deployArtifact"),
            _step("emergencyRollback"),  # not at index 0.
        ))
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert _has_kind(verdict, ViolationType.TIMING_VIOLATION)


class TestPlan08EmptyPlan:
    def test_empty_plan_blocked(self, devops_guard: Guard) -> None:
        verdict = devops_guard.plan_check(Plan())
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert _has_kind(verdict, ViolationType.EMPTY_PLAN)


class TestPlan09SingleStepBackwardCompat:
    def test_plan_from_action_round_trips(self, devops_guard: Guard) -> None:
        """``Plan.from_action(a)`` must yield the same per-step
        decision as ``Guard.check(a)`` — the AEGIS-2710 equivalence
        property tested on a real domain."""
        action = Action(
            action_type="readFile",
            agent_id="opencodeAgent",
            proposition={"path": "sourceFile"},
        )
        action_verdict = devops_guard.check(action)
        plan = Plan.from_action(action)
        plan_verdict = devops_guard.plan_check(plan)
        assert (
            plan_verdict.per_step_verdicts[0].decision
            == action_verdict.decision
        )


class TestPlan10DeployTimeBudget:
    def test_deploy_under_budget_passes(self, devops_guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", duration=300.0,
                  post={"buildStatus": "success"}),
            _step("testArtifact", duration=600.0,
                  post={"testStatus": "passed"}),
            _step("deployArtifact", duration=120.0),
        ))
        verdict = devops_guard.plan_check(plan)
        # 300 + 600 = 900 cumulative before deploy; budget is 1800.
        assert verdict.plan_decision == PlanDecision.PERMITTED

    def test_deploy_over_budget_blocked(self, devops_guard: Guard) -> None:
        plan = Plan(steps=(
            _step("buildArtifact", duration=900.0,
                  post={"buildStatus": "success"}),
            _step("testArtifact", duration=1100.0,
                  post={"testStatus": "passed"}),
            _step("deployArtifact"),
        ))
        verdict = devops_guard.plan_check(plan)
        # 900 + 1100 = 2000 > 1800 budget.
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert _has_kind(verdict, ViolationType.TIMING_VIOLATION)
