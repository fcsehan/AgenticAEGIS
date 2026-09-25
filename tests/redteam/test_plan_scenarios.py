"""Tests for AEGIS-2717 — Plan-level red-team scenarios."""

from __future__ import annotations

from aegis.guard.plan import ViolationType
from aegis.guard.verdict import PlanDecision
from aegis.redteam.plan_scenarios import (
    build_plan_scenarios,
    run_plan_scenarios,
)

# ── 1. Scenario library structure ─────────────────────────────────


class TestScenarioLibrary:
    def test_six_canonical_scenarios_exist(self) -> None:
        scenarios = build_plan_scenarios()
        assert len(scenarios) == 6
        ids = [s.scenario_id for s in scenarios]
        assert ids == [
            "RT-PLAN-01", "RT-PLAN-02", "RT-PLAN-03",
            "RT-PLAN-04", "RT-PLAN-05", "RT-PLAN-06",
        ]

    def test_each_has_description_and_plan(self) -> None:
        for s in build_plan_scenarios():
            assert s.description
            assert s.plan is not None

    def test_residual_risks_documented(self) -> None:
        scenarios = build_plan_scenarios()
        rt02 = next(s for s in scenarios if s.scenario_id == "RT-PLAN-02")
        rt04 = next(s for s in scenarios if s.scenario_id == "RT-PLAN-04")
        assert rt02.residual_risk_id == "R-2"
        assert rt04.residual_risk_id == "R-4"


# ── 2. Per-scenario expected verdict ──────────────────────────────


class TestPerScenarioVerdict:
    def test_rt_plan_01_smuggling_blocked(self) -> None:
        report = run_plan_scenarios()
        outcome = next(o for o in report.outcomes if o.scenario_id == "RT-PLAN-01")
        assert outcome.actual_decision == PlanDecision.FORBIDDEN
        assert ViolationType.PRECONDITION_VIOLATION in outcome.actual_violation_types

    def test_rt_plan_02_aggregate_blocked(self) -> None:
        report = run_plan_scenarios()
        outcome = next(o for o in report.outcomes if o.scenario_id == "RT-PLAN-02")
        assert outcome.actual_decision == PlanDecision.FORBIDDEN
        assert ViolationType.AGGREGATE_VIOLATION in outcome.actual_violation_types

    def test_rt_plan_03_sequence_blocked(self) -> None:
        report = run_plan_scenarios()
        outcome = next(o for o in report.outcomes if o.scenario_id == "RT-PLAN-03")
        assert outcome.actual_decision == PlanDecision.FORBIDDEN
        assert ViolationType.SEQUENCE_VIOLATION in outcome.actual_violation_types

    def test_rt_plan_04_state_fabrication_advisory_passes(self) -> None:
        """RT-PLAN-04 documents an I3-boundary residual risk: caller
        declares state, AEGIS doesn't verify it. Expected = PERMITTED."""
        report = run_plan_scenarios()
        outcome = next(o for o in report.outcomes if o.scenario_id == "RT-PLAN-04")
        assert outcome.expected_decision == PlanDecision.PERMITTED
        assert outcome.actual_decision == PlanDecision.PERMITTED
        # Resisted because expected matches actual.
        assert outcome.resisted
        assert not outcome.bypassed

    def test_rt_plan_05_timing_blocked(self) -> None:
        report = run_plan_scenarios()
        outcome = next(o for o in report.outcomes if o.scenario_id == "RT-PLAN-05")
        assert outcome.actual_decision == PlanDecision.FORBIDDEN
        assert ViolationType.TIMING_VIOLATION in outcome.actual_violation_types

    def test_rt_plan_06_obligation_uncovered_blocked(self) -> None:
        report = run_plan_scenarios()
        outcome = next(o for o in report.outcomes if o.scenario_id == "RT-PLAN-06")
        # require_obligation_coverage=True for this scenario flips the
        # module flag; oughtToDo reportIncident is in the DevOps domain
        # rules, so the missing reportIncident step triggers the
        # OBLIGATION_UNCOVERED violation.
        assert outcome.actual_decision == PlanDecision.FORBIDDEN
        assert (
            ViolationType.OBLIGATION_UNCOVERED in outcome.actual_violation_types
        )


# ── 3. Aggregate report invariant: bypass count = 0 ──────────────


class TestBypassInvariant:
    def test_no_scenario_bypasses_perimeter(self) -> None:
        report = run_plan_scenarios()
        bypassed = [o.scenario_id for o in report.outcomes if o.bypassed]
        assert bypassed == [], (
            f"Plan-perimeter bypass detected for: {bypassed}. "
            f"This is a security regression — the bypass count must "
            f"be 0 at all times."
        )
        assert report.all_resisted
        assert report.bypass_count == 0

    def test_average_plan_check_under_50ms(self) -> None:
        """Sanity: even adversarial scenarios should evaluate fast.
        50 ms average is generous for 6 small plans on a developer
        laptop and catches obvious regressions in plan_check."""
        report = run_plan_scenarios()
        assert report.average_plan_check_ms < 50.0


# ── 4. PlanScenarioOutcome.resisted semantics ────────────────────


class TestResistedSemantics:
    def test_forbidden_expected_undecidable_actual_still_resisted(self) -> None:
        """If a forbidden plan ends up UNDECIDABLE, the perimeter
        still held — the action did not get a green light."""
        from aegis.redteam.plan_scenarios import PlanScenarioOutcome
        outcome = PlanScenarioOutcome(
            scenario_id="synthetic",
            expected_decision=PlanDecision.FORBIDDEN,
            actual_decision=PlanDecision.UNDECIDABLE,
            expected_violation_types=(),
            actual_violation_types=(),
            plan_check_ms=1.0,
            bypassed=False,
        )
        assert outcome.resisted

    def test_forbidden_expected_permitted_actual_is_bypass(self) -> None:
        from aegis.redteam.plan_scenarios import PlanScenarioOutcome
        outcome = PlanScenarioOutcome(
            scenario_id="synthetic",
            expected_decision=PlanDecision.FORBIDDEN,
            actual_decision=PlanDecision.PERMITTED,
            expected_violation_types=(),
            actual_violation_types=(),
            plan_check_ms=1.0,
            bypassed=True,
        )
        assert not outcome.resisted
