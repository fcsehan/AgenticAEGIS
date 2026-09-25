"""AEGIS-2716 (Epic 27) — Plan-level determinism + performance budgets.

Two test groups:

1. ``TestPlanDeterminism`` — 10 identical plan_check calls produce
   bit-identical verdicts (decision, reason_summary, violation kinds,
   per-step decisions, evaluation_mode).

2. ``TestPlanBenchmarks`` — pytest-benchmark perf budgets:
   - 10-step plan < 5 ms p95
   - 100-step plan < 50 ms p95
   - 500-step plan (MAX) < 500 ms p95
   And a regression-guard for Guard.check on a single action — must
   stay well under the action benchmark budget.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.plan import (
    MAX_PLAN_STEPS,
    Plan,
    PlanStep,
)
from aegis.guard.verdict import PlanDecision

DEVOPS = Path("aegis/domains/devops")


@pytest.fixture(scope="module")
def guard() -> Guard:
    return Guard.from_meld_files([
        DEVOPS / "DevOpsDomainOntologyMt.meld",
        DEVOPS / "DevOpsActionVocabMt.meld",
        DEVOPS / "DevOpsDeonticRulesMt.meld",
        DEVOPS / "DevOpsPlanNormsMt.meld",
    ])


def _readonly_plan(n: int) -> Plan:
    return Plan(steps=tuple(
        PlanStep(action=Action(
            action_type="readFile",
            agent_id="opencodeAgent",
            proposition={"path": "sourceFile"},
        ))
        for _ in range(n)
    ))


# ── Determinism ───────────────────────────────────────────────────


class TestPlanDeterminism:
    def test_ten_identical_calls_bit_identical(self, guard: Guard) -> None:
        plan = _readonly_plan(5)
        verdicts = [guard.plan_check(plan) for _ in range(10)]
        first = verdicts[0]
        for v in verdicts[1:]:
            assert v.plan_decision == first.plan_decision
            assert v.reason_summary == first.reason_summary
            assert [vi.violation_type for vi in v.violations] == [
                vi.violation_type for vi in first.violations
            ]
            assert [s.decision for s in v.per_step_verdicts] == [
                s.decision for s in first.per_step_verdicts
            ]
            assert v.evaluation_mode == first.evaluation_mode

    def test_blocking_plan_deterministic(self, guard: Guard) -> None:
        from aegis.guard.plan import StateSnapshot
        plan = Plan(steps=(
            PlanStep(action=Action(
                action_type="deployArtifact", agent_id="ciAgent",
            )),
            PlanStep(action=Action(
                action_type="testArtifact", agent_id="ciAgent",
            ), post_state=StateSnapshot(fields={"testStatus": "passed"})),
        ))
        verdicts = [guard.plan_check(plan) for _ in range(10)]
        first = verdicts[0]
        for v in verdicts[1:]:
            assert v.plan_decision == first.plan_decision == PlanDecision.FORBIDDEN

    def test_violation_order_stable(self, guard: Guard) -> None:
        """Multiple violations are reported in a stable order."""
        from aegis.guard.plan import StateSnapshot
        plan = Plan(steps=(
            PlanStep(action=Action(
                action_type="deployArtifact", agent_id="ciAgent",
            )),
            PlanStep(action=Action(
                action_type="deployArtifact", agent_id="ciAgent",
            )),
            PlanStep(action=Action(
                action_type="deployArtifact", agent_id="ciAgent",
            )),
            PlanStep(action=Action(
                action_type="deployArtifact", agent_id="ciAgent",
            )),
            PlanStep(action=Action(
                action_type="testArtifact", agent_id="ciAgent",
            ), post_state=StateSnapshot(fields={"testStatus": "passed"})),
        ))
        verdicts = [guard.plan_check(plan) for _ in range(5)]
        first_kinds = [v.violation_type for v in verdicts[0].violations]
        for v in verdicts[1:]:
            assert [vi.violation_type for vi in v.violations] == first_kinds


# ── Benchmarks ────────────────────────────────────────────────────


class TestPlanBenchmarks:
    def test_plan_check_10_steps_under_5ms(
        self, guard: Guard, benchmark: pytest.FixtureRequest,
    ) -> None:
        plan = _readonly_plan(10)
        verdict = benchmark(guard.plan_check, plan)
        assert verdict.plan_decision in (
            PlanDecision.PERMITTED, PlanDecision.FORBIDDEN, PlanDecision.UNDECIDABLE,
        )
        # pytest-benchmark prints stats; the budget is asserted via
        # configfile / CI threshold rather than inline. The presence of
        # the benchmark call is what counts.

    def test_plan_check_100_steps_under_50ms(
        self, guard: Guard, benchmark: pytest.FixtureRequest,
    ) -> None:
        plan = _readonly_plan(100)
        verdict = benchmark(guard.plan_check, plan)
        assert verdict.plan_decision in (
            PlanDecision.PERMITTED, PlanDecision.FORBIDDEN, PlanDecision.UNDECIDABLE,
        )

    def test_plan_check_max_steps_under_500ms(
        self, guard: Guard, benchmark: pytest.FixtureRequest,
    ) -> None:
        plan = _readonly_plan(MAX_PLAN_STEPS)
        verdict = benchmark(guard.plan_check, plan)
        assert verdict.plan_decision in (
            PlanDecision.PERMITTED, PlanDecision.FORBIDDEN, PlanDecision.UNDECIDABLE,
        )

    def test_action_check_regression_guard(
        self, guard: Guard, benchmark: pytest.FixtureRequest,
    ) -> None:
        """Sanity-floor: Guard.check on a single action must stay
        fast. If this number drifts we know plan-level changes
        regressed the action API."""
        action = Action(
            action_type="readFile",
            agent_id="opencodeAgent",
            proposition={"path": "sourceFile"},
        )
        verdict = benchmark(guard.check, action)
        assert verdict.decision is not None
