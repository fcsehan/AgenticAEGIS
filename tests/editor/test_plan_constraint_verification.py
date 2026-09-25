"""Tests for AEGIS-2707 — Plan-Constraint Verification Pipeline."""

from __future__ import annotations

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.editor.plan_constraint_verification import (
    PlanStageStatus,
    verify_plan_constraints,
)
from aegis.engine.ddic_ir import (
    DDICCompound,
    DDICInteger,
    DDICLayer,
    DDICMode,
    DDICPlanConstraint,
    DDICPolarity,
    DDICSymbol,
    PlanConstraintKind,
)
from aegis.guard.registry import ActionTypeRegistry
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader


def _ddic_constraint(
    kind: PlanConstraintKind,
    *args: object,
    constraint_id: str | None = None,
    source_ref: str = "test.meld:1",
    layer: DDICLayer = DDICLayer.TESTIMONY,
    mode: DDICMode | None = None,
) -> DDICPlanConstraint:
    """Build a DDICPlanConstraint with sensible defaults."""
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
        source_ref=source_ref,
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


def _registry_with_actions(*action_types: str) -> ActionTypeRegistry:
    """Build a real ActionTypeRegistry containing the given action-types
    by loading a synthetic .meld vocabulary."""
    kb = KnowledgeBase()
    loader = MeldLoader(kb)
    lines = ["(case OpsVocab)"]
    for at in action_types:
        # The vocabulary loader keys off (isa <X> SoftwareAction) /
        # similar — but ActionTypeRegistry.from_kb runs VocabularyLoader
        # which wants ``isa <X> Action-Generic``. Use a generic ISA here.
        lines.append(f"(isa {at} ActionType)")
    loader.load_string("\n".join(lines), file="vocab.meld")
    kb.freeze()
    return ActionTypeRegistry.from_kb(kb)


# ── 1. Empty + happy path ─────────────────────────────────────────


class TestHappyPath:
    def test_empty_constraints_passes(self) -> None:
        result = verify_plan_constraints(())
        assert result.passed
        # All three stages produce a result (no short-circuit).
        assert [s.stage for s in result.stages] == [
            "symbol",
            "conflict",
            "functional",
        ]
        assert result.plan_constraint_cycles == []
        assert result.plan_constraint_conflicts == []

    def test_well_formed_constraint_passes(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "runTests", "deploy",
        )
        result = verify_plan_constraints((c,))
        assert result.passed
        # Functional always SKIP for now.
        assert result.stages[2].status == PlanStageStatus.SKIP

    def test_no_short_circuit(self) -> None:
        """Even when symbol fails, conflict + functional still run."""
        bad = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", "not-an-int",
        )
        result = verify_plan_constraints((bad,))
        assert not result.passed
        # All three stages produced a result.
        statuses = [s.status for s in result.stages]
        assert statuses[0] == PlanStageStatus.FAIL
        # conflict still ran (no short-circuit)
        assert statuses[1] in {
            PlanStageStatus.PASS, PlanStageStatus.FAIL,
        }


# ── 2. Symbol stage — argument shape ──────────────────────────────


class TestSymbolStageShape:
    def test_forbid_aggregate_threshold_must_be_integer(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", "many",
        )
        result = verify_plan_constraints((c,))
        assert not result.passed
        symbol = result.stages[0]
        assert symbol.status == PlanStageStatus.FAIL
        assert any(
            "threshold must be an integer" in i
            for i in symbol.details["issues"]
        )

    def test_forbid_aggregate_negative_threshold(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", -1,
        )
        result = verify_plan_constraints((c,))
        assert not result.passed
        assert any(
            "threshold must be >= 0" in i
            for i in result.stages[0].details["issues"]
        )

    def test_obligate_within_unknown_symbol(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_WITHIN, "deploy", "nextTuesday",
        )
        result = verify_plan_constraints((c,))
        assert not result.passed
        assert any(
            "timeframe must be integer" in i
            for i in result.stages[0].details["issues"]
        )

    def test_obligate_within_negative_seconds(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_WITHIN, "deploy", -5,
        )
        result = verify_plan_constraints((c,))
        assert not result.passed
        assert any(
            "must be >= 0" in i for i in result.stages[0].details["issues"]
        )

    def test_obligate_within_valid_symbol_and_int(self) -> None:
        cs = (
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_WITHIN, "alert", "immediate",
                constraint_id="c1",
            ),
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_WITHIN, "alert", 60,
                constraint_id="c2",
            ),
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_WITHIN, "alert", "same-session",
                constraint_id="c3",
            ),
        )
        result = verify_plan_constraints(cs)
        assert result.stages[0].status == PlanStageStatus.PASS

    def test_require_precondition_rejects_naked_integer(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.REQUIRE_PRECONDITION, "deploy", 42,
        )
        result = verify_plan_constraints((c,))
        assert not result.passed
        assert any(
            "must be a predicate" in i
            for i in result.stages[0].details["issues"]
        )


# ── 3. Symbol stage — action-type registry ────────────────────────


class TestSymbolStageRegistry:
    def test_unknown_action_type_flagged(self) -> None:
        registry = _registry_with_actions("runTests", "deploy")
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "runTests", "phantomOp",
        )
        # Note: only args[0] is checked as action-type in the symbol
        # stage — sequence-targets are handled by the cycle detector.
        # Use a constraint where args[0] is the unknown one for clarity.
        c2 = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "phantomOp", 3,
        )
        result = verify_plan_constraints((c, c2), registry=registry)
        assert not result.passed
        msgs = result.stages[0].details["issues"]
        assert any("phantomOp" in m for m in msgs)

    def test_known_action_type_passes(self) -> None:
        registry = _registry_with_actions("runTests", "deploy")
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 3,
        )
        result = verify_plan_constraints((c,), registry=registry)
        assert result.stages[0].status == PlanStageStatus.PASS

    def test_no_registry_means_skip_action_type_check(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.OBLIGATE_SEQUENCE, "anyName", "anotherName",
        )
        result = verify_plan_constraints((c,), registry=None)
        # Symbol stage still passes — only shape matters without
        # registry.
        assert result.stages[0].status == PlanStageStatus.PASS


# ── 4. Conflict stage — cycle detection ────────────────────────────


class TestConflictStageCycles:
    def test_two_node_cycle_detected(self) -> None:
        cs = (
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_SEQUENCE, "A", "B",
                constraint_id="seq:1",
            ),
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_SEQUENCE, "B", "A",
                constraint_id="seq:2",
            ),
        )
        result = verify_plan_constraints(cs)
        assert not result.passed
        assert len(result.plan_constraint_cycles) == 1
        # Canonical cycle starts with min element.
        cycle = result.plan_constraint_cycles[0]
        assert cycle[0] == cycle[-1]
        assert set(cycle) == {"A", "B"}

    def test_three_node_cycle_detected(self) -> None:
        cs = (
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_SEQUENCE, "A", "B",
                constraint_id="seq:1",
            ),
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_SEQUENCE, "B", "C",
                constraint_id="seq:2",
            ),
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_SEQUENCE, "C", "A",
                constraint_id="seq:3",
            ),
        )
        result = verify_plan_constraints(cs)
        assert not result.passed
        assert len(result.plan_constraint_cycles) == 1
        assert set(result.plan_constraint_cycles[0]) == {"A", "B", "C"}

    def test_dag_has_no_cycles(self) -> None:
        cs = (
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_SEQUENCE, "A", "B",
                constraint_id="seq:1",
            ),
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_SEQUENCE, "B", "C",
                constraint_id="seq:2",
            ),
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_SEQUENCE, "A", "C",
                constraint_id="seq:3",
            ),
        )
        result = verify_plan_constraints(cs)
        assert result.passed
        assert result.plan_constraint_cycles == []

    def test_self_loop_detected(self) -> None:
        cs = (
            _ddic_constraint(
                PlanConstraintKind.OBLIGATE_SEQUENCE, "A", "A",
                constraint_id="seq:self",
            ),
        )
        result = verify_plan_constraints(cs)
        assert not result.passed
        assert any("A" in cyc for cyc in result.plan_constraint_cycles)


# ── 5. Conflict stage — forbid-zero vs obligation ─────────────────


class TestConflictStageObligationContradiction:
    def test_forbid_aggregate_zero_vs_oblige(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 0,
            constraint_id="agg:0",
        )
        oblig = NormFrame(
            code="",
            agent_pattern="opsTeam",
            modality=DeonticModality.OBLIGATORY,
            proposition=("deploy",),
            source="rules.meld:5",
        )
        result = verify_plan_constraints((c,), existing_norms=[oblig])
        assert not result.passed
        assert len(result.plan_constraint_conflicts) == 1
        conflict = result.plan_constraint_conflicts[0]
        assert conflict["action_type"] == "deploy"
        assert conflict["obligated_by_agent"] == "opsTeam"

    def test_forbid_aggregate_one_does_not_contradict(self) -> None:
        """forbid-aggregate threshold=1 does NOT contradict an
        obligation — the action may still happen once."""
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 1,
        )
        oblig = NormFrame(
            code="",
            agent_pattern="opsTeam",
            modality=DeonticModality.OBLIGATORY,
            proposition=("deploy",),
        )
        result = verify_plan_constraints((c,), existing_norms=[oblig])
        assert result.passed

    def test_forbid_zero_without_matching_obligation_passes(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", 0,
        )
        unrelated = NormFrame(
            code="",
            agent_pattern="opsTeam",
            modality=DeonticModality.OBLIGATORY,
            proposition=("monitor",),
        )
        result = verify_plan_constraints((c,), existing_norms=[unrelated])
        assert result.passed


# ── 6. Result-flag surface ─────────────────────────────────────────


class TestResultSurface:
    def test_to_dict_round_trip(self) -> None:
        c = _ddic_constraint(
            PlanConstraintKind.FORBID_AGGREGATE, "deploy", -1,
        )
        result = verify_plan_constraints((c,))
        d = result.to_dict()
        assert d["passed"] is False
        assert "plan_constraint_cycles" in d
        assert "plan_constraint_conflicts" in d
        assert len(d["stages"]) == 3

    def test_functional_stage_always_present_skipped(self) -> None:
        result = verify_plan_constraints(())
        functional = result.stages[2]
        assert functional.stage == "functional"
        assert functional.status == PlanStageStatus.SKIP
        assert "AEGIS-2708" in functional.message
