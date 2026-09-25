"""Tests for AEGIS-2710 — PlanPipeline + Guard.plan_check integration.

Covers the equivalence-by-construction property, the aggregation table,
obligation coverage, and the D-007 limit handling at the Guard layer.
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


def _write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def ops_guard(tmp_path: Path) -> Guard:
    """Permissive ops domain with a few rules + plan-constraints."""
    onto = _write(tmp_path, "onto.meld", """
        (case OpsOntologyMt)
        (isa runTests SoftwareAction)
        (isa deploy SoftwareAction)
        (isa lint SoftwareAction)
        (isa monitor SoftwareAction)
    """)
    rules = _write(tmp_path, "rules.meld", """
        (case OpsRulesMt)
        (permittedToDo opsAgent runTests)
        (permittedToDo opsAgent deploy)
        (permittedToDo opsAgent lint)
        (permittedToDo opsAgent monitor)
        (forbiddenToDo opsAgent danger)
        (obligateSequence runTests deploy)
        (forbidAggregate deploy 2)
    """)
    return Guard.from_meld_files([onto, rules])


@pytest.fixture
def coverage_guard(tmp_path: Path) -> Guard:
    """Domain with an oughtToDo norm to test obligation coverage."""
    onto = _write(tmp_path, "onto.meld", """
        (case CoverOntoMt)
        (isa runTests SoftwareAction)
        (isa deploy SoftwareAction)
    """)
    rules = _write(tmp_path, "rules.meld", """
        (case CoverRulesMt)
        (permittedToDo opsAgent runTests)
        (permittedToDo opsAgent deploy)
        (oughtToDo opsAgent runTests)
    """)
    return Guard.from_meld_files([onto, rules])


# ── 1. Equivalence-by-construction ────────────────────────────────


class TestActionEquivalence:
    """AEGIS-2710 acceptance #2 (KRITISCH):
    ``Guard.plan_check(Plan.from_action(a)).per_step_verdicts[0].decision
     == Guard.check(a).decision``.
    """

    def test_permitted_action_round_trips(self, ops_guard: Guard) -> None:
        action = Action(action_type="runTests", agent_id="opsAgent")
        action_verdict = ops_guard.check(action)
        plan_verdict = ops_guard.plan_check(Plan.from_action(action))
        assert (
            plan_verdict.per_step_verdicts[0].decision
            == action_verdict.decision
        )

    def test_forbidden_action_round_trips(self, ops_guard: Guard) -> None:
        action = Action(action_type="danger", agent_id="opsAgent")
        action_verdict = ops_guard.check(action)
        plan_verdict = ops_guard.plan_check(Plan.from_action(action))
        assert (
            plan_verdict.per_step_verdicts[0].decision
            == action_verdict.decision
        )
        assert plan_verdict.plan_decision == PlanDecision.FORBIDDEN

    def test_unknown_action_round_trips(self, ops_guard: Guard) -> None:
        action = Action(action_type="phantomOp", agent_id="opsAgent")
        action_verdict = ops_guard.check(action)
        plan_verdict = ops_guard.plan_check(Plan.from_action(action))
        assert (
            plan_verdict.per_step_verdicts[0].decision
            == action_verdict.decision
        )


# ── 2. Aggregation table ──────────────────────────────────────────


class TestAggregation:
    def test_all_permitted_no_violations_executable(
        self, ops_guard: Guard,
    ) -> None:
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="runTests", agent_id="opsAgent")),
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
        ))
        verdict = ops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED
        assert verdict.violations == ()

    def test_one_forbidden_step_blocks_plan(self, ops_guard: Guard) -> None:
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="runTests", agent_id="opsAgent")),
            PlanStep(action=Action(action_type="danger", agent_id="opsAgent")),
        ))
        verdict = ops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert "step_forbidden" in verdict.reason_summary

    def test_sequence_violation_blocks_plan(self, ops_guard: Guard) -> None:
        # deploy before runTests violates the obligateSequence.
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
            PlanStep(action=Action(action_type="runTests", agent_id="opsAgent")),
        ))
        verdict = ops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        kinds = {v.violation_type for v in verdict.violations}
        assert ViolationType.SEQUENCE_VIOLATION in kinds

    def test_aggregate_violation_blocks_plan(self, ops_guard: Guard) -> None:
        plan = Plan(steps=tuple(
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent"))
            for _ in range(3)
        ))
        verdict = ops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        kinds = {v.violation_type for v in verdict.violations}
        assert ViolationType.AGGREGATE_VIOLATION in kinds

    def test_unknown_step_with_blocking_violation_is_forbidden(
        self, ops_guard: Guard,
    ) -> None:
        """Fail-closed: UNDECIDABLE per step + blocking violation =>
        FORBIDDEN, per the AEGIS-2710 aggregation rule #5."""
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="phantomOp", agent_id="opsAgent")),
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
        ))
        verdict = ops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN

    def test_unknown_step_alone_is_undecidable(self, ops_guard: Guard) -> None:
        # phantomOp → UNDECIDABLE step; no plan-level violation.
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="phantomOp", agent_id="opsAgent")),
        ))
        verdict = ops_guard.plan_check(plan)
        # Domain is open: phantomOp not in registry → UNDECIDABLE.
        assert verdict.plan_decision == PlanDecision.UNDECIDABLE


# ── 3. Obligation coverage ────────────────────────────────────────


class TestObligationCoverage:
    def test_coverage_report_lists_match(self, coverage_guard: Guard) -> None:
        from aegis.guard.plan_pipeline import PlanPipeline
        pipeline = PlanPipeline(coverage_guard)
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="runTests", agent_id="opsAgent")),
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
        ))
        coverage = pipeline.coverage(plan)
        assert any(
            m.matched_action_type == "runTests" for m in coverage.matches
        )
        assert coverage.uncovered_obligation_ids == ()

    def test_coverage_uncovered_when_obligation_missing(
        self, coverage_guard: Guard,
    ) -> None:
        from aegis.guard.plan_pipeline import PlanPipeline
        pipeline = PlanPipeline(coverage_guard)
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
        ))
        coverage = pipeline.coverage(plan)
        # runTests obligation isn't covered.
        assert coverage.uncovered_obligation_ids != ()

    def test_default_coverage_off_so_no_violation(
        self, coverage_guard: Guard,
    ) -> None:
        """Olson's open question: require_obligation_coverage is opt-in.
        With the default (off), an uncovered obligation must NOT yield
        a plan-level violation."""
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
        ))
        verdict = coverage_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED
        kinds = {v.violation_type for v in verdict.violations}
        assert ViolationType.OBLIGATION_UNCOVERED not in kinds


# ── 4. D-007 limits at the Guard layer ────────────────────────────


class TestLimitHandling:
    def test_too_many_steps_undecidable(self, ops_guard: Guard) -> None:
        from aegis.guard.plan import MAX_PLAN_STEPS
        big_plan = Plan(steps=tuple(
            PlanStep(action=Action(action_type="runTests", agent_id="opsAgent"))
            for _ in range(MAX_PLAN_STEPS + 1)
        ))
        verdict = ops_guard.plan_check(big_plan)
        assert verdict.plan_decision == PlanDecision.UNDECIDABLE
        assert "d_007" in verdict.reason_summary or "limit" in verdict.reason_summary

    def test_oversized_state_undecidable(self, ops_guard: Guard) -> None:
        from aegis.guard.plan import MAX_STATE_FIELDS
        big_state = StateSnapshot(
            fields={f"k_{i}": i for i in range(MAX_STATE_FIELDS + 1)},
        )
        plan = Plan(
            steps=(
                PlanStep(action=Action(action_type="runTests", agent_id="opsAgent")),
            ),
            initial_state=big_state,
        )
        verdict = ops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.UNDECIDABLE


# ── 5. Empty plan rejection ────────────────────────────────────────


class TestEmptyPlanAtGuard:
    def test_empty_plan_forbidden(self, ops_guard: Guard) -> None:
        verdict = ops_guard.plan_check(Plan())
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        kinds = {v.violation_type for v in verdict.violations}
        assert ViolationType.EMPTY_PLAN in kinds


# ── 6. Per-step verdict preservation ─────────────────────────────


class TestPerStepVerdictPreservation:
    def test_per_step_verdicts_carry_action_type(self, ops_guard: Guard) -> None:
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="runTests", agent_id="opsAgent")),
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
        ))
        verdict = ops_guard.plan_check(plan)
        types = [v.action_type for v in verdict.per_step_verdicts]
        assert types == ["runTests", "deploy"]

    def test_per_step_verdicts_carry_agent(self, ops_guard: Guard) -> None:
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="runTests", agent_id="opsAgent")),
        ))
        verdict = ops_guard.plan_check(plan)
        assert verdict.per_step_verdicts[0].agent_id == "opsAgent"


# ── 7. State propagation through pipeline ─────────────────────────


class TestStatePropagation:
    """Per AEGIS-2710 + 2709: post_state of step N feeds pre_state of
    N+1 through the pipeline."""

    def test_post_to_next_pre_propagates(self, tmp_path: Path) -> None:
        onto = _write(tmp_path, "onto.meld", """
            (case Pmt)
            (isa runTests SoftwareAction)
            (isa deploy SoftwareAction)
        """)
        rules = _write(tmp_path, "rules.meld", """
            (case PrMt)
            (permittedToDo opsAgent runTests)
            (permittedToDo opsAgent deploy)
            (requirePrecondition deploy (testStatus passed))
        """)
        guard = Guard.from_meld_files([onto, rules])
        plan = Plan(steps=(
            PlanStep(
                action=Action(action_type="runTests", agent_id="opsAgent"),
                post_state=StateSnapshot(fields={"testStatus": "passed"}),
            ),
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
        ))
        verdict = guard.plan_check(plan)
        # precondition met → PERMITTED.
        assert verdict.plan_decision == PlanDecision.PERMITTED

    def test_missing_post_blocks_precondition(self, tmp_path: Path) -> None:
        onto = _write(tmp_path, "onto.meld", """
            (case Pmt)
            (isa runTests SoftwareAction)
            (isa deploy SoftwareAction)
        """)
        rules = _write(tmp_path, "rules.meld", """
            (case PrMt)
            (permittedToDo opsAgent runTests)
            (permittedToDo opsAgent deploy)
            (requirePrecondition deploy (testStatus passed))
        """)
        guard = Guard.from_meld_files([onto, rules])
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="runTests", agent_id="opsAgent")),
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
        ))
        verdict = guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        kinds = {v.violation_type for v in verdict.violations}
        assert ViolationType.PRECONDITION_VIOLATION in kinds


# ── 8. Existing Guard.check unchanged ─────────────────────────────


class TestActionApiUntouched:
    def test_check_still_returns_same_decision(self, ops_guard: Guard) -> None:
        action = Action(action_type="runTests", agent_id="opsAgent")
        v = ops_guard.check(action)
        assert v.decision == Decision.PERMITTED

    def test_check_forbidden_unchanged(self, ops_guard: Guard) -> None:
        action = Action(action_type="danger", agent_id="opsAgent")
        v = ops_guard.check(action)
        assert v.decision == Decision.FORBIDDEN
