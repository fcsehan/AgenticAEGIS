"""Tests for the Plan / PlanStep / StateSnapshot data model
(AEGIS-2701, Epic 27)."""

from __future__ import annotations

from aegis.guard.action import Action
from aegis.guard.plan import (
    MAX_PLAN_STEPS,
    MAX_STATE_FIELDS,
    ObligationCoverage,
    ObligationMatch,
    Plan,
    PlanStep,
    PlanViolation,
    StateSnapshot,
    ViolationType,
)


class TestViolationTypeEnum:
    def test_eight_variants(self) -> None:
        """AEGIS-2701 acceptance: ViolationType has 8 variants."""
        assert len(list(ViolationType)) == 8

    def test_canonical_variants_present(self) -> None:
        names = {v.name for v in ViolationType}
        assert names == {
            "SEQUENCE_VIOLATION",
            "AGGREGATE_VIOLATION",
            "TIMING_VIOLATION",
            "PRECONDITION_VIOLATION",
            "STEP_FORBIDDEN",
            "STEP_UNDECIDABLE",
            "OBLIGATION_UNCOVERED",
            "EMPTY_PLAN",
        }


class TestPlanFromAction:
    def test_round_trip_property(self) -> None:
        """AEGIS-2701 acceptance property: Plan.from_action(a).steps[0].action == a."""
        action = Action(
            action_type="share",
            agent_id="agent-1",
            proposition={"recipient": "alice"},
        )
        plan = Plan.from_action(action)
        assert len(plan.steps) == 1
        assert plan.steps[0].action == action

    def test_action_unmodified(self) -> None:
        """The action sits in the step verbatim — no field rewriting."""
        action = Action(
            action_type="x",
            agent_id="y",
            user_intent="show me x",
        )
        plan = Plan.from_action(action)
        assert plan.steps[0].action.user_intent == "show me x"


class TestEmptyPlan:
    def test_empty_plan_constructible(self) -> None:
        """AEGIS-2701: empty plans are representable; semantic
        rejection happens later."""
        plan = Plan()
        assert plan.steps == ()
        # validate_limits passes — the empty-plan rejection is the
        # evaluator's job (ViolationType.EMPTY_PLAN).
        assert plan.validate_limits() == []


class TestValidateLimits:
    def test_default_plan_passes(self) -> None:
        action = Action(action_type="share", agent_id="agent")
        plan = Plan.from_action(action)
        assert plan.validate_limits() == []

    def test_too_many_steps_violates(self) -> None:
        action = Action(action_type="x", agent_id="y")
        steps = tuple(PlanStep(action=action) for _ in range(MAX_PLAN_STEPS + 1))
        plan = Plan(steps=steps)
        violations = plan.validate_limits()
        assert any("steps" in v for v in violations)

    def test_too_many_initial_state_fields_violates(self) -> None:
        big_state = StateSnapshot(
            fields={f"k_{i}": i for i in range(MAX_STATE_FIELDS + 1)},
        )
        plan = Plan(initial_state=big_state)
        violations = plan.validate_limits()
        assert any("initial_state" in v for v in violations)

    def test_too_many_per_step_state_fields_violates(self) -> None:
        action = Action(action_type="x", agent_id="y")
        big_state = StateSnapshot(
            fields={f"k_{i}": i for i in range(MAX_STATE_FIELDS + 1)},
        )
        step = PlanStep(action=action, pre_state=big_state)
        plan = Plan(steps=(step,))
        violations = plan.validate_limits()
        assert any("pre_state" in v for v in violations)


class TestToFacts:
    def test_facts_include_plan_root(self) -> None:
        action = Action(action_type="share", agent_id="agent-1")
        plan = Plan.from_action(action)
        facts = plan.to_facts()
        assert any(f[0] == "plan" for f in facts)

    def test_facts_include_per_step_marker(self) -> None:
        action = Action(action_type="share", agent_id="agent-1")
        plan = Plan.from_action(action)
        facts = plan.to_facts()
        assert any(f[0] == "planStep" for f in facts)

    def test_facts_include_underlying_action_facts(self) -> None:
        action = Action(
            action_type="share",
            agent_id="agent-1",
            proposition={"recipient": "alice"},
        )
        plan = Plan.from_action(action)
        facts = plan.to_facts()
        assert any(f[0] == "action" for f in facts)
        assert any(f[0] == "actionField" for f in facts)


class TestImmutability:
    def test_plan_is_frozen(self) -> None:
        plan = Plan()
        try:
            plan.plan_id = "x"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("Plan must be frozen")

    def test_planstep_is_frozen(self) -> None:
        action = Action(action_type="x", agent_id="y")
        step = PlanStep(action=action)
        try:
            step.step_id = "x"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("PlanStep must be frozen")

    def test_state_snapshot_is_frozen(self) -> None:
        snapshot = StateSnapshot(fields={"k": 1})
        try:
            snapshot.fields = {"k": 2}  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("StateSnapshot must be frozen")

    def test_plan_violation_is_frozen(self) -> None:
        v = PlanViolation(violation_type=ViolationType.STEP_FORBIDDEN)
        try:
            v.detail = "x"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("PlanViolation must be frozen")


class TestObligationTypes:
    def test_match_round_trip(self) -> None:
        m = ObligationMatch(
            obligation_id="oblig-1",
            matched_step_index=2,
            matched_action_type="approveDeploy",
        )
        assert m.matched_step_index == 2

    def test_coverage_default_empty(self) -> None:
        c = ObligationCoverage()
        assert c.matches == ()
        assert c.uncovered_obligation_ids == ()


class TestStateSnapshotIsolation:
    def test_post_init_copies_dict(self) -> None:
        """The dict passed in must be defensively copied so caller
        mutations don't affect the snapshot."""
        external = {"k": 1}
        snapshot = StateSnapshot(fields=external)
        external["k"] = 999
        assert snapshot.fields == {"k": 1}
