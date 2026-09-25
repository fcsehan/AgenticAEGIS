"""Tests for the v1 NormFrame → DDICModule compilation bridge.

Verifies that every NormFrame maps losslessly to a DDICFormula, and that the
compiled DDICModule has the correct structure and metadata.
"""

from __future__ import annotations

import pytest

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic_ir import (
    DDICCompound,
    DDICLayer,
    DDICMode,
    DDICPolarity,
    DDICSymbol,
)
from aegis.engine.normframe_compile import (
    compile_norms_to_module,
    formula_code,
    formula_is_axiom,
)

# ── Fixtures ────────────────────────────────────────────────────────


def _norm(
    code: str = "",
    agent: str = "*",
    modality: DeonticModality = DeonticModality.FORBIDDEN,
    proposition: tuple[object, ...] = ("doSomething",),
    specificity: int = 0,
    defeasible: bool = True,
    source: str = "test.meld:1",
) -> NormFrame:
    return NormFrame(
        code=code,
        agent_pattern=agent,
        modality=modality,
        proposition=proposition,
        specificity=specificity,
        defeasible=defeasible,
        source=source,
    )


# ── Basic Compilation ───────────────────────────────────────────────


class TestNormToFormula:
    def test_forbidden_maps_to_forbidden(self) -> None:
        module = compile_norms_to_module([_norm(modality=DeonticModality.FORBIDDEN)])
        assert len(module.formulas) == 1
        assert module.formulas[0].mode == DDICMode.FORBIDDEN

    def test_obligatory_maps_to_obligatory(self) -> None:
        module = compile_norms_to_module(
            [_norm(modality=DeonticModality.OBLIGATORY)]
        )
        assert module.formulas[0].mode == DDICMode.OBLIGATORY

    def test_permitted_maps_to_optional(self) -> None:
        module = compile_norms_to_module(
            [_norm(modality=DeonticModality.PERMITTED)]
        )
        assert module.formulas[0].mode == DDICMode.OPTIONAL

    def test_layer_is_always_testimony(self) -> None:
        module = compile_norms_to_module([_norm()])
        assert module.formulas[0].layer == DDICLayer.TESTIMONY

    def test_polarity_is_always_positive(self) -> None:
        module = compile_norms_to_module([_norm()])
        assert module.formulas[0].polarity == DDICPolarity.POSITIVE

    def test_agent_becomes_symbol(self) -> None:
        module = compile_norms_to_module([_norm(agent="intelligenceAgent")])
        assert module.formulas[0].agent == DDICSymbol("intelligenceAgent")

    def test_wildcard_agent_preserved(self) -> None:
        module = compile_norms_to_module([_norm(agent="*")])
        assert module.formulas[0].agent == DDICSymbol("*")

    def test_context_is_top(self) -> None:
        module = compile_norms_to_module([_norm()])
        assert module.formulas[0].context == DDICSymbol("Top")

    def test_time_is_t0(self) -> None:
        module = compile_norms_to_module([_norm()])
        assert module.formulas[0].time == DDICSymbol("t0")

    def test_source_ref_preserved(self) -> None:
        module = compile_norms_to_module([_norm(source="rules.meld:42")])
        assert module.formulas[0].source_ref == "rules.meld:42"
        assert module.formulas[0].formula_id == "rules.meld:42"


# ── Proposition → Behavior ──────────────────────────────────────────


class TestPropositionToBehavior:
    def test_single_atom(self) -> None:
        module = compile_norms_to_module([_norm(proposition=("doSomething",))])
        assert module.formulas[0].behavior == DDICSymbol("doSomething")

    def test_compound_proposition(self) -> None:
        module = compile_norms_to_module(
            [_norm(proposition=("shareIntelligence", "classified", "externalService"))]
        )
        expected = DDICCompound(
            head="shareIntelligence",
            args=(DDICSymbol("classified"), DDICSymbol("externalService")),
        )
        assert module.formulas[0].behavior == expected

    def test_nested_proposition(self) -> None:
        module = compile_norms_to_module(
            [_norm(proposition=("sendData", "personal"))]
        )
        expected = DDICCompound(
            head="sendData", args=(DDICSymbol("personal"),)
        )
        assert module.formulas[0].behavior == expected


# ── Module Structure ────────────────────────────────────────────────


class TestModuleStructure:
    def test_resolution_strategy_is_legacy(self) -> None:
        module = compile_norms_to_module([_norm()])
        assert module.resolution_strategy == "legacy"

    def test_code_prevalence_stored(self) -> None:
        module = compile_norms_to_module(
            [_norm()], code_prevalence=["IAMissionCode", "DevSecOps"]
        )
        assert module.code_prevalence == ("IAMissionCode", "DevSecOps")

    def test_no_defaults_or_rules(self) -> None:
        module = compile_norms_to_module([_norm()])
        assert module.defaults == ()
        assert module.defeasible_rules == ()
        assert module.priorities == ()

    def test_empty_norms(self) -> None:
        module = compile_norms_to_module([])
        assert module.formulas == ()
        assert module.resolution_strategy == "legacy"


# ── Metadata ────────────────────────────────────────────────────────


class TestMetadata:
    def test_code_stored_as_metadata(self) -> None:
        module = compile_norms_to_module(
            [_norm(code="IAMissionCode", source="r.meld:1")]
        )
        code = formula_code(module.formulas[0], module)
        assert code == "IAMissionCode"

    def test_no_code_means_empty_string(self) -> None:
        module = compile_norms_to_module([_norm(code="")])
        code = formula_code(module.formulas[0], module)
        assert code == ""

    def test_axiom_tracked(self) -> None:
        module = compile_norms_to_module(
            [_norm(defeasible=False, source="axiom.meld:1")]
        )
        assert formula_is_axiom(module.formulas[0], module) is True

    def test_defeasible_is_not_axiom(self) -> None:
        module = compile_norms_to_module(
            [_norm(defeasible=True, source="rule.meld:1")]
        )
        assert formula_is_axiom(module.formulas[0], module) is False


# ── Multiple Norms ──────────────────────────────────────────────────


class TestMultipleNorms:
    def test_all_norms_compiled(self) -> None:
        norms = [
            _norm(source="a.meld:1", modality=DeonticModality.FORBIDDEN),
            _norm(source="a.meld:2", modality=DeonticModality.PERMITTED),
            _norm(source="a.meld:3", modality=DeonticModality.OBLIGATORY),
        ]
        module = compile_norms_to_module(norms)
        assert len(module.formulas) == 3
        modes = {f.mode for f in module.formulas}
        assert modes == {DDICMode.FORBIDDEN, DDICMode.OPTIONAL, DDICMode.OBLIGATORY}

    def test_formula_ids_unique(self) -> None:
        norms = [
            _norm(source="a.meld:1"),
            _norm(source="a.meld:2"),
            _norm(source="a.meld:3"),
        ]
        module = compile_norms_to_module(norms)
        ids = [f.formula_id for f in module.formulas]
        assert len(ids) == len(set(ids))


# ── AEGIS-2705 — Plan-Constraint Compilation (Epic 27) ─────────────


from aegis.deontic.plan_norm_frame import PlanNormFrame  # noqa: E402
from aegis.engine.ddic_ir import (  # noqa: E402
    DDICInteger,
    PlanConstraintKind,
)
from aegis.engine.normframe_compile import (  # noqa: E402
    compile_plan_constraints_to_module,
)


def _frame(
    predicate: str,
    *args: object,
    agent_pattern: str = "*",
    source: str = "p.meld:1",
    specificity: int = 0,
    defeasible: bool = True,
) -> PlanNormFrame:
    return PlanNormFrame(
        predicate=predicate,
        args=tuple(args),
        agent_pattern=agent_pattern,
        source=source,
        specificity=specificity,
        defeasible=defeasible,
    )


class TestPlanConstraintCompilation:
    def test_obligate_sequence_maps_to_obligatory(self) -> None:
        constraints = compile_plan_constraints_to_module(
            [_frame("obligateSequence", "runTests", "deploy")]
        )
        assert len(constraints) == 1
        c = constraints[0]
        assert c.kind == PlanConstraintKind.OBLIGATE_SEQUENCE
        assert c.layer == DDICLayer.TESTIMONY
        assert c.mode == DDICMode.OBLIGATORY
        assert c.polarity == DDICPolarity.POSITIVE

    def test_forbid_aggregate_maps_to_forbidden(self) -> None:
        constraints = compile_plan_constraints_to_module(
            [_frame("forbidAggregate", "deploy", 3)]
        )
        c = constraints[0]
        assert c.kind == PlanConstraintKind.FORBID_AGGREGATE
        assert c.mode == DDICMode.FORBIDDEN
        # Args term-compiled: string → DDICSymbol, int → DDICInteger.
        assert c.args == (DDICSymbol("deploy"), DDICInteger(3))

    def test_obligate_within_maps_to_obligatory(self) -> None:
        constraints = compile_plan_constraints_to_module(
            [_frame("obligateWithin", "alert", "immediate")]
        )
        c = constraints[0]
        assert c.kind == PlanConstraintKind.OBLIGATE_WITHIN
        assert c.mode == DDICMode.OBLIGATORY
        assert c.args == (DDICSymbol("alert"), DDICSymbol("immediate"))

    def test_require_precondition_lives_on_belief_layer(self) -> None:
        """Per AEGIS-2705 acceptance: ``requirePrecondition`` is a
        state constraint and therefore lands on layer=BELIEF."""
        constraints = compile_plan_constraints_to_module(
            [_frame("requirePrecondition", "deploy", ("testStatus", "passed"))]
        )
        c = constraints[0]
        assert c.kind == PlanConstraintKind.REQUIRE_PRECONDITION
        assert c.layer == DDICLayer.BELIEF
        assert c.mode == DDICMode.OBLIGATORY
        # Compound argument: state predicate becomes a DDICCompound.
        assert isinstance(c.args[1], DDICCompound)
        assert c.args[1].head == "testStatus"
        assert c.args[1].args == (DDICSymbol("passed"),)

    def test_default_agent_pattern_wildcard(self) -> None:
        constraints = compile_plan_constraints_to_module(
            [_frame("obligateSequence", "a", "b")]
        )
        assert constraints[0].agent_pattern == DDICSymbol("*")

    def test_explicit_agent_pattern_propagated(self) -> None:
        constraints = compile_plan_constraints_to_module(
            [_frame("obligateSequence", "a", "b", agent_pattern="opsTeam")]
        )
        assert constraints[0].agent_pattern == DDICSymbol("opsTeam")

    def test_source_ref_propagated(self) -> None:
        constraints = compile_plan_constraints_to_module(
            [_frame("forbidAggregate", "deploy", 1, source="domain.meld:42")]
        )
        assert constraints[0].source_ref == "domain.meld:42"

    def test_specificity_and_defeasibility_propagated(self) -> None:
        constraints = compile_plan_constraints_to_module(
            [_frame("obligateSequence", "a", "b", specificity=5, defeasible=False)]
        )
        c = constraints[0]
        assert c.specificity == 5
        assert c.defeasible is False

    def test_input_order_preserved(self) -> None:
        frames = [
            _frame("obligateSequence", "a", "b", source="m.meld:1"),
            _frame("forbidAggregate", "deploy", 2, source="m.meld:2"),
            _frame("obligateWithin", "alert", "immediate", source="m.meld:3"),
        ]
        constraints = compile_plan_constraints_to_module(frames)
        assert [c.source_ref for c in constraints] == [
            "m.meld:1",
            "m.meld:2",
            "m.meld:3",
        ]

    def test_constraint_ids_unique(self) -> None:
        frames = [
            _frame("obligateSequence", "a", "b"),
            _frame("obligateSequence", "c", "d"),
        ]
        constraints = compile_plan_constraints_to_module(frames)
        ids = [c.constraint_id for c in constraints]
        assert len(ids) == len(set(ids))

    def test_unrecognised_predicate_raises(self) -> None:
        """Defensive — a future MELD-extension that adds a predicate
        without updating the mapping must surface loudly."""
        bogus = PlanNormFrame(predicate="future-predicate", args=("x",))
        with pytest.raises(ValueError, match="out of sync"):
            compile_plan_constraints_to_module([bogus])


class TestCompileV1NormsToModuleAttachesPlanConstraints:
    """The wrapper compile_norms_to_module attaches plan-constraints
    to the produced DDICModule (AEGIS-2705 acceptance)."""

    def test_default_module_has_no_plan_constraints(self) -> None:
        module = compile_norms_to_module([_norm()])
        assert module.plan_constraints == ()
        assert module.require_obligation_coverage is False

    def test_plan_constraints_attached_to_module(self) -> None:
        module = compile_norms_to_module(
            [_norm()],
            plan_constraints=[
                _frame("obligateSequence", "runTests", "deploy"),
                _frame("forbidAggregate", "deploy", 3),
            ],
        )
        assert len(module.plan_constraints) == 2
        kinds = {c.kind for c in module.plan_constraints}
        assert kinds == {
            PlanConstraintKind.OBLIGATE_SEQUENCE,
            PlanConstraintKind.FORBID_AGGREGATE,
        }

    def test_resolution_strategy_still_legacy(self) -> None:
        module = compile_norms_to_module(
            [_norm()],
            plan_constraints=[_frame("obligateSequence", "a", "b")],
        )
        assert module.resolution_strategy == "legacy"

    def test_existing_signature_backward_compatible(self) -> None:
        """Calling without the new kwarg still works (None default)."""
        module = compile_norms_to_module([_norm()], code_prevalence=["A", "B"])
        assert module.plan_constraints == ()
        assert module.code_prevalence == ("A", "B")
