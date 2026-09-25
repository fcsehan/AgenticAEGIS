"""Tests for MELD v2-DDIC AST -> IR compilation."""

from __future__ import annotations

from aegis.engine.ddic_ir import (
    DDICDefeatMode,
    DDICFormula,
    DDICFormulaPattern,
    DDICModule,
    DDICPolarity,
    compile_meld_module,
)
from aegis.kb.meld_loader import parse_meld_module


class TestCompileMeldModule:
    def test_compiles_normative_formula_to_ir(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (testimony-obligatory AgentA WearHelmet OnBike t1)
            """,
            file="compile-formula.meld",
        )

        ir = compile_meld_module(module)

        assert isinstance(ir, DDICModule)
        assert len(ir.formulas) == 1
        formula = ir.formulas[0]
        assert isinstance(formula, DDICFormula)
        assert formula.layer.value == "testimony"
        assert formula.mode.value == "obligatory"
        assert formula.polarity == DDICPolarity.POSITIVE
        assert formula.agent.value == "AgentA"
        assert formula.behavior.value == "WearHelmet"
        assert formula.context.value == "OnBike"
        assert formula.time.value == "t1"
        assert formula.source_ref == "compile-formula.meld:3"

    def test_compiles_relation_to_ir(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (behavior-subsumes HelpCookVegetables HelpCook)
            """,
            file="compile-relation.meld",
        )

        ir = compile_meld_module(module)

        assert len(ir.relations) == 1
        relation = ir.relations[0]
        assert relation.kind.value == "behavior-subsumes"
        assert relation.args[0].value == "HelpCookVegetables"
        assert relation.args[1].value == "HelpCook"

    def test_compiles_default_rule_to_ir(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (default-rule D1b
              (implies
                (testimony-obligatory ?A ?B ?C ?T)
                (not-testimony-forbidden ?A ?B ?C ?T)))
            """,
            file="compile-default.meld",
        )

        ir = compile_meld_module(module)

        assert len(ir.defaults) == 1
        rule = ir.defaults[0]
        assert rule.rule_id == "D1b"
        assert len(rule.body) == 1
        assert isinstance(rule.head, DDICFormulaPattern)
        assert rule.head.layer.value == "testimony"
        assert rule.head.mode.value == "forbidden"
        assert rule.head.polarity == DDICPolarity.NEGATIVE

    def test_compiles_defeasible_rule_to_ir(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (defeasible-rule R3
              :from (testimony-forbidden ?A ?C ?Phi ?T)
              :to   (belief-forbidden ?A ?B ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification
                     ((testimony-forbidden ?A ?Z ?Psi ?Tx)
                      (between-inclusive ?T ?Tx ?Tn))
              :defeat-mode partial)
            """,
            file="compile-defeasible.meld",
        )

        ir = compile_meld_module(module)

        assert len(ir.defeasible_rules) == 1
        rule = ir.defeasible_rules[0]
        assert rule.rule_id == "R3"
        assert isinstance(rule.antecedent, DDICFormulaPattern)
        assert isinstance(rule.consequent, DDICFormulaPattern)
        assert len(rule.guards) == 3
        assert len(rule.justification_schema) == 2
        assert rule.defeat_mode == DDICDefeatMode.PARTIAL

    def test_compiles_priority_to_ir(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (priority D1b R3)
            """,
            file="compile-priority.meld",
        )

        ir = compile_meld_module(module)

        assert len(ir.priorities) == 1
        edge = ir.priorities[0]
        assert edge.higher == "D1b"
        assert edge.lower == "R3"


class TestPlanConstraintIR:
    """AEGIS-2703 (Epic 27): the IR carries plan-level constraints."""

    def test_plan_constraint_kind_has_four_variants(self) -> None:
        from aegis.engine.ddic_ir import PlanConstraintKind
        assert {k.name for k in PlanConstraintKind} == {
            "OBLIGATE_SEQUENCE",
            "FORBID_AGGREGATE",
            "OBLIGATE_WITHIN",
            "REQUIRE_PRECONDITION",
        }

    def test_plan_constraint_kind_values_kebab_case(self) -> None:
        """AEGIS-2703 acceptance: IR values are kebab-case."""
        from aegis.engine.ddic_ir import PlanConstraintKind
        assert PlanConstraintKind.OBLIGATE_SEQUENCE.value == "obligate-sequence"
        assert PlanConstraintKind.FORBID_AGGREGATE.value == "forbid-aggregate"
        assert PlanConstraintKind.OBLIGATE_WITHIN.value == "obligate-within"
        assert PlanConstraintKind.REQUIRE_PRECONDITION.value == "require-precondition"

    def test_ddic_plan_constraint_has_required_fields(self) -> None:
        from aegis.engine.ddic_ir import (
            DDICLayer,
            DDICMode,
            DDICPlanConstraint,
            DDICPolarity,
            DDICSymbol,
            PlanConstraintKind,
        )
        c = DDICPlanConstraint(
            constraint_id="seq-1",
            kind=PlanConstraintKind.OBLIGATE_SEQUENCE,
            args=(DDICSymbol("A"), DDICSymbol("B")),
            source_ref="test.meld:1",
        )
        assert c.constraint_id == "seq-1"
        assert c.kind == PlanConstraintKind.OBLIGATE_SEQUENCE
        assert c.layer == DDICLayer.BELIEF  # default
        assert c.mode == DDICMode.OBLIGATORY  # default
        assert c.polarity == DDICPolarity.POSITIVE  # default
        assert c.specificity == 0
        assert c.defeasible is True
        assert c.agent_pattern == DDICSymbol("*")

    def test_ddic_module_default_has_empty_plan_constraints(self) -> None:
        module = DDICModule(
            formulas=(), relations=(), defaults=(),
            defeasible_rules=(), priorities=(),
        )
        assert module.plan_constraints == ()
        assert module.require_obligation_coverage is False

    def test_ddic_module_can_carry_plan_constraints(self) -> None:
        from aegis.engine.ddic_ir import (
            DDICPlanConstraint,
            DDICSymbol,
            PlanConstraintKind,
        )
        c = DDICPlanConstraint(
            constraint_id="agg-1",
            kind=PlanConstraintKind.FORBID_AGGREGATE,
            args=(DDICSymbol("deploy"), DDICSymbol("3")),
            source_ref="x",
        )
        module = DDICModule(
            formulas=(), relations=(), defaults=(),
            defeasible_rules=(), priorities=(),
            plan_constraints=(c,),
            require_obligation_coverage=True,
        )
        assert module.plan_constraints == (c,)
        assert module.require_obligation_coverage is True

    def test_plan_constraint_is_frozen(self) -> None:
        from aegis.engine.ddic_ir import (
            DDICPlanConstraint,
            PlanConstraintKind,
        )
        c = DDICPlanConstraint(
            constraint_id="x",
            kind=PlanConstraintKind.OBLIGATE_SEQUENCE,
            source_ref="x",
        )
        try:
            c.constraint_id = "y"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("DDICPlanConstraint must be frozen")


class TestModuleMerge:
    """AEGIS-2703 acceptance: _merge_ddic_modules merges
    plan_constraints by concatenation and require_obligation_coverage
    by OR."""

    def test_merge_concatenates_plan_constraints(self) -> None:
        from aegis.engine.ddic_ir import (
            DDICPlanConstraint,
            PlanConstraintKind,
        )
        from aegis.guard.guard import _merge_ddic_modules

        c1 = DDICPlanConstraint(
            constraint_id="a", kind=PlanConstraintKind.OBLIGATE_SEQUENCE,
            source_ref="x",
        )
        c2 = DDICPlanConstraint(
            constraint_id="b", kind=PlanConstraintKind.FORBID_AGGREGATE,
            source_ref="y",
        )
        m1 = DDICModule(
            formulas=(), relations=(), defaults=(),
            defeasible_rules=(), priorities=(),
            plan_constraints=(c1,),
        )
        m2 = DDICModule(
            formulas=(), relations=(), defaults=(),
            defeasible_rules=(), priorities=(),
            plan_constraints=(c2,),
        )
        merged = _merge_ddic_modules([m1, m2])
        assert merged.plan_constraints == (c1, c2)

    def test_merge_obligation_coverage_or_semantics(self) -> None:
        from aegis.guard.guard import _merge_ddic_modules

        m_off = DDICModule(
            formulas=(), relations=(), defaults=(),
            defeasible_rules=(), priorities=(),
            require_obligation_coverage=False,
        )
        m_on = DDICModule(
            formulas=(), relations=(), defaults=(),
            defeasible_rules=(), priorities=(),
            require_obligation_coverage=True,
        )
        # Even one ON in the inputs flips merged to ON.
        assert _merge_ddic_modules([m_off, m_on]).require_obligation_coverage is True
        assert _merge_ddic_modules([m_off, m_off]).require_obligation_coverage is False
