"""Tests for AEGIS-2708 — Plan-Evaluator Core."""

from __future__ import annotations

import pytest

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic_eval import DDICVerdict, evaluate_legacy_module
from aegis.engine.ddic_ir import DDICModule
from aegis.engine.normframe_compile import compile_norms_to_module
from aegis.engine.plan_eval import (
    MAX_PLAN_STEPS_CORE,
    PlanCoreOutcome,
    PlanCoreViolation,
    PlanCoreViolationKind,
    PlanStepView,
    PlanView,
    evaluate_plan_module,
)

# ── Fixtures ──────────────────────────────────────────────────────


def _norm(
    modality: DeonticModality,
    proposition: tuple[object, ...] = ("doSomething",),
    agent: str = "*",
    source: str = "test.meld:1",
) -> NormFrame:
    return NormFrame(
        code="",
        agent_pattern=agent,
        modality=modality,
        proposition=proposition,
        source=source,
    )


def _module_v1(*norms: NormFrame) -> DDICModule:
    return compile_norms_to_module(list(norms))


def _step(
    index: int,
    action_type: str,
    agent: str = "agent-1",
    duration: float = 0.0,
    pre: dict | None = None,
    post: dict | None = None,
) -> PlanStepView:
    return PlanStepView(
        step_index=index,
        action_type=action_type,
        agent=agent,
        proposition=(action_type,),
        scheduled_duration_s=duration,
        pre_state_fields=pre or {},
        post_state_fields=post or {},
    )


# ── 1. Empty / over-budget sentinels ──────────────────────────────


class TestEmptyAndOverBudget:
    def test_empty_plan_blocked(self) -> None:
        module = _module_v1()
        result = evaluate_plan_module(module, PlanView(steps=()))
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED
        assert result.reason_summary == "empty_plan"
        assert any(
            v.kind == PlanCoreViolationKind.EMPTY_PLAN
            for v in result.plan_violations_core
        )

    def test_plan_too_long_undecidable(self) -> None:
        module = _module_v1(_norm(DeonticModality.PERMITTED))
        steps = tuple(
            _step(i, "doSomething") for i in range(MAX_PLAN_STEPS_CORE + 1)
        )
        result = evaluate_plan_module(module, PlanView(steps=steps))
        assert result.overall_outcome == PlanCoreOutcome.UNDECIDABLE
        assert result.reason_summary == "plan_too_long"
        assert any(
            v.kind == PlanCoreViolationKind.PLAN_TOO_LONG
            for v in result.plan_violations_core
        )
        assert any(
            "R-5" in v.detail for v in result.plan_violations_core
        )

    def test_plan_at_max_size_evaluates(self) -> None:
        """Off-by-one: exactly MAX_PLAN_STEPS_CORE steps must NOT
        trigger PLAN_TOO_LONG."""
        module = _module_v1(_norm(DeonticModality.PERMITTED))
        steps = tuple(
            _step(i, "doSomething") for i in range(MAX_PLAN_STEPS_CORE)
        )
        result = evaluate_plan_module(module, PlanView(steps=steps))
        assert result.overall_outcome != PlanCoreOutcome.UNDECIDABLE or all(
            v.kind != PlanCoreViolationKind.PLAN_TOO_LONG
            for v in result.plan_violations_core
        )


# ── 2. Per-step delegation: 1-step plan ↔ Action equivalence ──────


class TestSingleStepEquivalence:
    """AEGIS-2708 acceptance #3: a 1-step plan delivers the same
    decision as ``evaluate_legacy_module`` on the underlying action."""

    def test_permitted_action_yields_executable(self) -> None:
        norm = _norm(DeonticModality.PERMITTED, ("doSomething",))
        module = _module_v1(norm)
        single = PlanView(steps=(_step(0, "doSomething"),))

        plan_result = evaluate_plan_module(module, single)
        direct_state = evaluate_legacy_module(
            module, ("doSomething",), "agent-1"
        )

        assert plan_result.overall_outcome == PlanCoreOutcome.EXECUTABLE
        assert plan_result.step_beliefs[0].derived_verdict == direct_state.verdict

    def test_forbidden_action_yields_blocked(self) -> None:
        norm = _norm(DeonticModality.FORBIDDEN, ("doSomething",))
        module = _module_v1(norm)
        single = PlanView(steps=(_step(0, "doSomething"),))

        plan_result = evaluate_plan_module(module, single)

        assert plan_result.overall_outcome == PlanCoreOutcome.BLOCKED
        assert plan_result.step_beliefs[0].derived_verdict == DDICVerdict.FORBIDDEN
        assert any(
            v.kind == PlanCoreViolationKind.STEP_FORBIDDEN
            for v in plan_result.plan_violations_core
        )

    def test_no_norm_yields_undecidable(self) -> None:
        # Empty module → no applicable norms → UNDECIDABLE per step.
        module = _module_v1()
        single = PlanView(steps=(_step(0, "doSomething"),))
        plan_result = evaluate_plan_module(module, single)
        assert plan_result.overall_outcome == PlanCoreOutcome.UNDECIDABLE
        assert plan_result.step_beliefs[0].derived_verdict == DDICVerdict.UNDECIDABLE


# ── 3. Multi-step plans ────────────────────────────────────────────


class TestMultiStepPlans:
    def test_all_permitted_steps_executable(self) -> None:
        module = _module_v1(
            _norm(DeonticModality.PERMITTED, ("doA",)),
            _norm(DeonticModality.PERMITTED, ("doB",)),
            _norm(DeonticModality.PERMITTED, ("doC",)),
        )
        plan = PlanView(steps=(
            _step(0, "doA"),
            _step(1, "doB"),
            _step(2, "doC"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE
        assert len(result.step_beliefs) == 3
        for b in result.step_beliefs:
            assert b.derived_verdict == DDICVerdict.PERMITTED

    def test_one_forbidden_step_blocks_plan(self) -> None:
        module = _module_v1(
            _norm(DeonticModality.PERMITTED, ("doA",)),
            _norm(DeonticModality.FORBIDDEN, ("doB",)),
            _norm(DeonticModality.PERMITTED, ("doC",)),
        )
        plan = PlanView(steps=(
            _step(0, "doA"),
            _step(1, "doB"),
            _step(2, "doC"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED
        # Per-step beliefs preserved for audit.
        assert len(result.step_beliefs) == 3
        assert result.step_beliefs[1].derived_verdict == DDICVerdict.FORBIDDEN

    def test_undecidable_without_forbidden(self) -> None:
        module = _module_v1(
            _norm(DeonticModality.PERMITTED, ("doA",)),
            # doB has no rule → UNDECIDABLE
            _norm(DeonticModality.PERMITTED, ("doC",)),
        )
        plan = PlanView(steps=(
            _step(0, "doA"),
            _step(1, "doB"),
            _step(2, "doC"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.UNDECIDABLE


# ── 4. State snapshot tracking ────────────────────────────────────


class TestStateSnapshots:
    def test_initial_state_visible_at_step_zero(self) -> None:
        module = _module_v1(_norm(DeonticModality.PERMITTED, ("doA",)))
        plan = PlanView(
            steps=(_step(0, "doA"),),
            initial_state_fields={"env": "prod"},
        )
        result = evaluate_plan_module(module, plan)
        assert result.step_snapshots[0]["env"] == "prod"

    def test_post_state_propagates_to_next_step(self) -> None:
        module = _module_v1(
            _norm(DeonticModality.PERMITTED, ("doA",)),
            _norm(DeonticModality.PERMITTED, ("doB",)),
        )
        plan = PlanView(steps=(
            _step(0, "doA", post={"testStatus": "passed"}),
            _step(1, "doB"),
        ))
        result = evaluate_plan_module(module, plan)
        assert "testStatus" not in result.step_snapshots[0]
        assert result.step_snapshots[1].get("testStatus") == "passed"

    def test_step_pre_state_overrides_running_state(self) -> None:
        module = _module_v1(
            _norm(DeonticModality.PERMITTED, ("doA",)),
            _norm(DeonticModality.PERMITTED, ("doB",)),
        )
        plan = PlanView(
            steps=(
                _step(0, "doA", post={"x": "v0"}),
                _step(1, "doB", pre={"x": "explicit"}),
            ),
        )
        result = evaluate_plan_module(module, plan)
        assert result.step_snapshots[1]["x"] == "explicit"


# ── 5. Determinism ─────────────────────────────────────────────────


class TestDeterminism:
    def test_identical_inputs_yield_identical_results(self) -> None:
        module = _module_v1(
            _norm(DeonticModality.PERMITTED, ("doA",)),
            _norm(DeonticModality.FORBIDDEN, ("doB",)),
        )
        plan = PlanView(steps=(
            _step(0, "doA"), _step(1, "doB"), _step(2, "doA"),
        ))
        r1 = evaluate_plan_module(module, plan)
        r2 = evaluate_plan_module(module, plan)
        assert r1.overall_outcome == r2.overall_outcome
        assert r1.reason_summary == r2.reason_summary
        assert len(r1.step_beliefs) == len(r2.step_beliefs)
        for b1, b2 in zip(r1.step_beliefs, r2.step_beliefs, strict=True):
            assert b1.derived_verdict == b2.derived_verdict


# ── 6. Output type purity (Core-only) ─────────────────────────────


class TestOutputTypePurity:
    """AEGIS-2708 acceptance #1: PlanEvaluationResult is a pure Core
    structure. Spot-check by importing it and asserting its module
    location lives under aegis.engine.*"""

    def test_result_module_is_core(self) -> None:
        from aegis.engine.plan_eval import PlanEvaluationResult
        assert PlanEvaluationResult.__module__.startswith("aegis.engine.")

    def test_violation_module_is_core(self) -> None:
        from aegis.engine.plan_eval import PlanCoreViolation
        assert PlanCoreViolation.__module__.startswith("aegis.engine.")


# ── 7. Default agent on permissive norms ───────────────────────────


class TestAgentMatching:
    def test_wildcard_agent_matches_step_agent(self) -> None:
        module = _module_v1(_norm(DeonticModality.PERMITTED, ("doA",), agent="*"))
        plan = PlanView(steps=(
            _step(0, "doA", agent="alice"),
            _step(1, "doA", agent="bob"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_specific_agent_filters(self) -> None:
        module = _module_v1(
            _norm(DeonticModality.PERMITTED, ("doA",), agent="alice"),
        )
        plan = PlanView(steps=(_step(0, "doA", agent="bob"),))
        result = evaluate_plan_module(module, plan)
        # bob has no rule → UNDECIDABLE
        assert result.step_beliefs[0].derived_verdict == DDICVerdict.UNDECIDABLE


# ── 8. Result structure ───────────────────────────────────────────


class TestResultStructure:
    def test_step_beliefs_indexed_by_step_index(self) -> None:
        module = _module_v1(_norm(DeonticModality.PERMITTED, ("doA",)))
        plan = PlanView(steps=(
            _step(0, "doA"), _step(1, "doA"), _step(2, "doA"),
        ))
        result = evaluate_plan_module(module, plan)
        for i, belief in enumerate(result.step_beliefs):
            assert belief.step_index == i

    def test_violations_carry_step_index(self) -> None:
        module = _module_v1(_norm(DeonticModality.FORBIDDEN, ("doA",)))
        plan = PlanView(steps=(_step(0, "doA"), _step(1, "doA")))
        result = evaluate_plan_module(module, plan)
        forbidden_violations = [
            v for v in result.plan_violations_core
            if v.kind == PlanCoreViolationKind.STEP_FORBIDDEN
        ]
        assert len(forbidden_violations) == 2
        assert {v.step_index for v in forbidden_violations} == {0, 1}


# ── 9. Frozen / immutable ─────────────────────────────────────────


class TestImmutability:
    def test_plan_view_is_frozen(self) -> None:
        view = PlanView(steps=())
        with pytest.raises(AttributeError):
            view.plan_id = "x"  # type: ignore[misc]

    def test_step_view_is_frozen(self) -> None:
        step = _step(0, "doA")
        with pytest.raises(AttributeError):
            step.action_type = "modified"  # type: ignore[misc]

    def test_violation_is_frozen(self) -> None:
        v = PlanCoreViolation(kind=PlanCoreViolationKind.EMPTY_PLAN)
        with pytest.raises(AttributeError):
            v.detail = "x"  # type: ignore[misc]


# ── AEGIS-2709 — Plan-Constraint Checks ───────────────────────────


from dataclasses import replace  # noqa: E402

from aegis.engine.ddic_ir import (  # noqa: E402
    DDICCompound,
    DDICInteger,
    DDICLayer,
    DDICMode,
    DDICPlanConstraint,
    DDICPolarity,
    DDICSymbol,
    PlanConstraintKind,
)


def _ddic_constraint(
    kind: PlanConstraintKind,
    *args: object,
    constraint_id: str | None = None,
    layer: DDICLayer = DDICLayer.TESTIMONY,
    mode: DDICMode | None = None,
) -> DDICPlanConstraint:
    if mode is None:
        mode = (
            DDICMode.FORBIDDEN
            if kind == PlanConstraintKind.FORBID_AGGREGATE
            else DDICMode.OBLIGATORY
        )
    if kind == PlanConstraintKind.REQUIRE_PRECONDITION:
        layer = DDICLayer.BELIEF
    compiled_args = tuple(_to_term(a) for a in args)
    return DDICPlanConstraint(
        constraint_id=constraint_id or f"plan-{kind.value}:0",
        kind=kind,
        args=compiled_args,
        layer=layer,
        mode=mode,
        polarity=DDICPolarity.POSITIVE,
        source_ref="test.meld:1",
    )


def _to_term(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError(value)
    if isinstance(value, int):
        return DDICInteger(value)
    if isinstance(value, str):
        return DDICSymbol(value)
    if isinstance(value, tuple):
        head, *rest = value
        return DDICCompound(
            head=str(head),
            args=tuple(_to_term(r) for r in rest),
        )
    return value


def _module_with_plan_constraints(
    norms: list[NormFrame],
    constraints: tuple[DDICPlanConstraint, ...],
) -> DDICModule:
    base = compile_norms_to_module(norms)
    return replace(base, plan_constraints=constraints)


def _permissive_module_for(
    *action_types: str,
    extra_constraints: tuple[DDICPlanConstraint, ...] = (),
) -> DDICModule:
    norms = [_norm(DeonticModality.PERMITTED, (a,)) for a in action_types]
    return _module_with_plan_constraints(norms, extra_constraints)


# ── obligateSequence ──────────────────────────────────────────────


class TestObligateSequence:
    def test_correct_order_passes(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "runTests", "deploy",
        )
        module = _permissive_module_for(
            "runTests", "deploy", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "runTests"), _step(1, "deploy"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_reverse_order_blocked(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "runTests", "deploy",
            constraint_id="seq:1",
        )
        module = _permissive_module_for(
            "runTests", "deploy", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "deploy"), _step(1, "runTests"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED
        assert any(
            v.kind == PlanCoreViolationKind.SEQUENCE
            and v.constraint_id == "seq:1"
            for v in result.plan_violations_core
        )

    def test_only_predecessor_no_violation(self) -> None:
        """obligate-sequence A B with only A in plan: not a violation,
        the sequence is conditional on co-occurrence."""
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "runTests", "deploy",
        )
        module = _permissive_module_for("runTests", extra_constraints=(c,))
        plan = PlanView(steps=(_step(0, "runTests"),))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_only_successor_no_violation(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "runTests", "deploy",
        )
        module = _permissive_module_for("deploy", extra_constraints=(c,))
        plan = PlanView(steps=(_step(0, "deploy"),))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_topological_not_just_adjacent(self) -> None:
        """obligate-sequence A B doesn't require adjacency — only
        order. A intervening step is fine."""
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "runTests", "deploy",
        )
        module = _permissive_module_for(
            "runTests", "lint", "deploy", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "runTests"), _step(1, "lint"), _step(2, "deploy"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_multiple_b_before_a_all_violate(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "runTests", "deploy",
            constraint_id="seq:multi",
        )
        module = _permissive_module_for(
            "runTests", "deploy", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "deploy"), _step(1, "deploy"), _step(2, "runTests"),
        ))
        result = evaluate_plan_module(module, plan)
        seq_violations = [
            v for v in result.plan_violations_core
            if v.kind == PlanCoreViolationKind.SEQUENCE
        ]
        assert len(seq_violations) == 2
        assert {v.step_index for v in seq_violations} == {0, 1}


# ── forbidAggregate ───────────────────────────────────────────────


class TestForbidAggregate:
    def test_count_within_threshold_passes(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 3,
        )
        module = _permissive_module_for("deploy", extra_constraints=(c,))
        plan = PlanView(steps=tuple(
            _step(i, "deploy") for i in range(3)
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_count_over_threshold_violates(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 3,
            constraint_id="agg:3",
        )
        module = _permissive_module_for("deploy", extra_constraints=(c,))
        plan = PlanView(steps=tuple(
            _step(i, "deploy") for i in range(4)
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED
        agg = next(
            v for v in result.plan_violations_core
            if v.kind == PlanCoreViolationKind.AGGREGATE
        )
        assert agg.constraint_id == "agg:3"
        # First excess at index 3 (the 4th occurrence — 0-indexed).
        assert agg.step_index == 3

    def test_threshold_zero_forbids_any_occurrence(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 0,
        )
        module = _permissive_module_for("deploy", extra_constraints=(c,))
        plan = PlanView(steps=(_step(0, "deploy"),))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED
        assert any(
            v.kind == PlanCoreViolationKind.AGGREGATE
            for v in result.plan_violations_core
        )

    def test_action_absent_no_violation(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 0,
        )
        module = _permissive_module_for("monitor", extra_constraints=(c,))
        plan = PlanView(steps=(_step(0, "monitor"),))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE


# ── obligateWithin ────────────────────────────────────────────────


class TestObligateWithin:
    def test_immediate_at_index_zero_passes(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_WITHIN, "alert", "immediate",
        )
        module = _permissive_module_for(
            "alert", "monitor", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "alert"), _step(1, "monitor"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_immediate_not_at_index_zero_violates(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_WITHIN, "alert", "immediate",
            constraint_id="within:imm",
        )
        module = _permissive_module_for(
            "alert", "monitor", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "monitor"), _step(1, "alert"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED
        assert any(
            v.kind == PlanCoreViolationKind.TIMING
            and v.constraint_id == "within:imm"
            for v in result.plan_violations_core
        )

    def test_within_seconds_under_budget_passes(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_WITHIN, "deploy", 60,
        )
        module = _permissive_module_for(
            "lint", "deploy", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "lint", duration=30.0),
            _step(1, "deploy", duration=10.0),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_within_seconds_over_budget_violates(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_WITHIN, "deploy", 60,
            constraint_id="within:n",
        )
        module = _permissive_module_for(
            "lint", "deploy", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "lint", duration=120.0),
            _step(1, "deploy", duration=10.0),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED
        assert any(
            v.kind == PlanCoreViolationKind.TIMING
            and v.constraint_id == "within:n"
            for v in result.plan_violations_core
        )

    def test_within_zero_with_first_step_passes(self) -> None:
        """obligate-within X 0 means X must be at index 0
        (cumulative duration before == 0)."""
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_WITHIN, "alert", 0,
        )
        module = _permissive_module_for("alert", extra_constraints=(c,))
        plan = PlanView(steps=(_step(0, "alert", duration=5.0),))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_session_level_symbols_treated_as_satisfied(self) -> None:
        """``same-session`` and ``end-of-plan`` are session-level —
        the in-plan evaluator treats them as always satisfied. The
        verifier may still warn about misuse."""
        for sym in ("same-session", "end-of-plan"):
            c = _ddic_constraint(
                PlanConstraintKind.OBLIGATE_WITHIN, "deploy", sym,
            )
            module = _permissive_module_for("deploy", extra_constraints=(c,))
            plan = PlanView(steps=(_step(0, "deploy"),))
            result = evaluate_plan_module(module, plan)
            assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_action_absent_no_violation(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_WITHIN, "alert", "immediate",
        )
        module = _permissive_module_for("monitor", extra_constraints=(c,))
        plan = PlanView(steps=(_step(0, "monitor"),))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE


# ── requirePrecondition ───────────────────────────────────────────


class TestRequirePrecondition:
    def test_precondition_holds_passes(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.REQUIRE_PRECONDITION,
            "deploy",
            ("testStatus", "passed"),
        )
        module = _permissive_module_for("deploy", extra_constraints=(c,))
        plan = PlanView(
            steps=(_step(0, "deploy", pre={"testStatus": "passed"}),),
        )
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_precondition_missing_violates(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.REQUIRE_PRECONDITION,
            "deploy",
            ("testStatus", "passed"),
            constraint_id="pre:1",
        )
        module = _permissive_module_for("deploy", extra_constraints=(c,))
        plan = PlanView(steps=(_step(0, "deploy"),))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED
        assert any(
            v.kind == PlanCoreViolationKind.PRECONDITION
            and v.constraint_id == "pre:1"
            for v in result.plan_violations_core
        )

    def test_precondition_wrong_value_violates(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.REQUIRE_PRECONDITION,
            "deploy",
            ("testStatus", "passed"),
        )
        module = _permissive_module_for("deploy", extra_constraints=(c,))
        plan = PlanView(
            steps=(_step(0, "deploy", pre={"testStatus": "failed"}),),
        )
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED

    def test_precondition_propagates_from_post_state(self) -> None:
        """post_state of step 0 must satisfy precondition of step 1."""
        c = _ddic_constraint(
            PlanConstraintKind.REQUIRE_PRECONDITION,
            "deploy",
            ("testStatus", "passed"),
        )
        module = _permissive_module_for(
            "runTests", "deploy", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "runTests", post={"testStatus": "passed"}),
            _step(1, "deploy"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_precondition_not_propagated_when_unset(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.REQUIRE_PRECONDITION,
            "deploy",
            ("testStatus", "passed"),
        )
        module = _permissive_module_for(
            "runTests", "deploy", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "runTests"),  # no post
            _step(1, "deploy"),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED

    def test_precondition_only_for_matching_action_type(self) -> None:
        """A precondition for action X does NOT apply to action Y."""
        c = _ddic_constraint(
            PlanConstraintKind.REQUIRE_PRECONDITION,
            "deploy",
            ("testStatus", "passed"),
        )
        module = _permissive_module_for(
            "monitor", "deploy", extra_constraints=(c,),
        )
        plan = PlanView(steps=(
            _step(0, "monitor"),  # no precondition required
            _step(1, "deploy", pre={"testStatus": "passed"}),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE


# ── State-progression specifics ───────────────────────────────────


class TestStateProgressionWithConstraints:
    def test_pre_state_seen_at_step_zero(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.REQUIRE_PRECONDITION,
            "deploy",
            ("env", "prod"),
        )
        module = _permissive_module_for("deploy", extra_constraints=(c,))
        plan = PlanView(
            steps=(_step(0, "deploy"),),
            initial_state_fields={"env": "prod"},
        )
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_initial_state_overridden_by_post_state(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.REQUIRE_PRECONDITION,
            "deploy",
            ("env", "prod"),
        )
        module = _permissive_module_for(
            "runTests", "deploy", extra_constraints=(c,),
        )
        plan = PlanView(
            steps=(
                _step(0, "runTests", post={"env": "stage"}),
                _step(1, "deploy"),
            ),
            initial_state_fields={"env": "prod"},
        )
        result = evaluate_plan_module(module, plan)
        # post_state overrode env, so deploy's precondition (env=prod) fails.
        assert result.overall_outcome == PlanCoreOutcome.BLOCKED


# ── Mixed constraint types & edge cases ──────────────────────────


class TestMixedConstraints:
    def test_multiple_constraint_kinds_all_pass(self) -> None:
        seq = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "runTests", "deploy",
        )
        agg = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 5,
        )
        within = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_WITHIN, "deploy", 60,
        )
        pre = _ddic_constraint(
            PlanConstraintKind.REQUIRE_PRECONDITION,
            "deploy",
            ("testStatus", "passed"),
        )
        module = _permissive_module_for(
            "runTests", "deploy",
            extra_constraints=(seq, agg, within, pre),
        )
        plan = PlanView(steps=(
            _step(0, "runTests", duration=10.0, post={"testStatus": "passed"}),
            _step(1, "deploy", duration=5.0),
        ))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_multiple_violations_reported_together(self) -> None:
        seq = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "runTests", "deploy",
            constraint_id="seq",
        )
        agg = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 0,
            constraint_id="agg",
        )
        module = _permissive_module_for(
            "runTests", "deploy", extra_constraints=(seq, agg),
        )
        plan = PlanView(steps=(
            _step(0, "deploy"),
            _step(1, "runTests"),
            _step(2, "deploy"),
        ))
        result = evaluate_plan_module(module, plan)
        kinds = {v.kind for v in result.plan_violations_core}
        assert PlanCoreViolationKind.SEQUENCE in kinds
        assert PlanCoreViolationKind.AGGREGATE in kinds


class TestEmptyConstraints:
    def test_no_constraints_no_violations(self) -> None:
        module = _permissive_module_for("runTests", "deploy")
        plan = PlanView(steps=(
            _step(0, "deploy"), _step(1, "runTests"),  # bad order…
        ))
        result = evaluate_plan_module(module, plan)
        # …but no constraint says it's a violation.
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE

    def test_one_step_plan_is_fine(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 1,
        )
        module = _permissive_module_for("deploy", extra_constraints=(c,))
        plan = PlanView(steps=(_step(0, "deploy"),))
        result = evaluate_plan_module(module, plan)
        assert result.overall_outcome == PlanCoreOutcome.EXECUTABLE


class TestDeterminismWithConstraints:
    def test_constraint_evaluation_is_deterministic(self) -> None:
        c1 = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "a", "b", constraint_id="c1",
        )
        c2 = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "b", 1, constraint_id="c2",
        )
        module = _permissive_module_for("a", "b", extra_constraints=(c1, c2))
        plan = PlanView(steps=(
            _step(0, "b"), _step(1, "b"), _step(2, "a"),
        ))
        r1 = evaluate_plan_module(module, plan)
        r2 = evaluate_plan_module(module, plan)
        assert r1.overall_outcome == r2.overall_outcome
        assert [v.kind for v in r1.plan_violations_core] == [
            v.kind for v in r2.plan_violations_core
        ]
