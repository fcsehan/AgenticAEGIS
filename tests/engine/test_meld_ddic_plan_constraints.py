"""Tests for AEGIS-2706 — MELD v2-DDIC plan-constraint extension.

The v2 surface forms (kebab-case canonical, camelCase alias) parse into
``PlanConstraintStatement`` AST nodes; ``compile_meld_module`` then
emits ``DDICPlanConstraint`` instances on the resulting ``DDICModule``.
"""

from __future__ import annotations

import pytest

from aegis.deontic import ddic_ast
from aegis.deontic.plan_norm_frame import PlanNormFrame
from aegis.engine.ddic_ir import (
    DDICCompound,
    DDICInteger,
    DDICLayer,
    DDICMode,
    DDICPolarity,
    DDICSymbol,
    PlanConstraintKind,
    compile_meld_module,
)
from aegis.engine.normframe_compile import compile_plan_constraints_to_module
from aegis.errors import MeldSyntaxError
from aegis.kb.meld_loader import parse_meld_module


def _module(text: str, file: str = "v2-plan.meld") -> ddic_ast.MeldModule:
    return parse_meld_module(text, file=file)


# ── 1. AST-level parsing ──────────────────────────────────────────


class TestPlanConstraintAstNode:
    def test_canonical_kebab_case_parsed(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (obligate-sequence runTests deploy)
            """
        )
        statements = [
            s for s in module.statements
            if isinstance(s, ddic_ast.PlanConstraintStatement)
        ]
        assert len(statements) == 1
        assert (
            statements[0].kind
            == ddic_ast.PlanConstraintKindAst.OBLIGATE_SEQUENCE
        )

    def test_camel_case_alias_normalised(self) -> None:
        """camelCase form parses to the same AST kind as kebab-case."""
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (obligateSequence runTests deploy)
            """
        )
        stmt = next(
            s for s in module.statements
            if isinstance(s, ddic_ast.PlanConstraintStatement)
        )
        assert (
            stmt.kind == ddic_ast.PlanConstraintKindAst.OBLIGATE_SEQUENCE
        )
        # Value is the kebab-case canonical, regardless of input form.
        assert stmt.kind.value == "obligate-sequence"

    def test_all_four_predicates_parse(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (obligate-sequence a b)
            (forbid-aggregate deploy 3)
            (obligate-within alert 60)
            (require-precondition deploy (testStatus passed))
            """
        )
        kinds = {
            s.kind for s in module.statements
            if isinstance(s, ddic_ast.PlanConstraintStatement)
        }
        assert kinds == {
            ddic_ast.PlanConstraintKindAst.OBLIGATE_SEQUENCE,
            ddic_ast.PlanConstraintKindAst.FORBID_AGGREGATE,
            ddic_ast.PlanConstraintKindAst.OBLIGATE_WITHIN,
            ddic_ast.PlanConstraintKindAst.REQUIRE_PRECONDITION,
        }

    def test_arity_violation_is_meld_syntax_error(self) -> None:
        with pytest.raises(MeldSyntaxError, match="expects exactly 2 arguments"):
            _module(
                """
                (aegis-schema-version 2)
                (case OpsMt)
                (obligate-sequence onlyOne)
                """
            )

    def test_three_args_fails(self) -> None:
        with pytest.raises(MeldSyntaxError, match="expects exactly 2"):
            _module(
                """
                (aegis-schema-version 2)
                (case OpsMt)
                (forbid-aggregate deploy 3 surplus)
                """
            )


# ── 2. IR-compilation ──────────────────────────────────────────────


class TestIrCompilation:
    def test_module_carries_compiled_plan_constraints(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (obligate-sequence runTests deploy)
            (forbid-aggregate deploy 3)
            """
        )
        ir = compile_meld_module(module)
        assert len(ir.plan_constraints) == 2

    def test_kind_mapping_is_kebab_case(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (forbid-aggregate deploy 3)
            """
        )
        ir = compile_meld_module(module)
        c = ir.plan_constraints[0]
        assert c.kind == PlanConstraintKind.FORBID_AGGREGATE
        assert c.kind.value == "forbid-aggregate"

    def test_layer_mode_polarity_per_kind(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (obligate-sequence a b)
            (forbid-aggregate deploy 3)
            (obligate-within alert 60)
            (require-precondition deploy (testStatus passed))
            """
        )
        ir = compile_meld_module(module)
        by_kind = {c.kind: c for c in ir.plan_constraints}

        assert (
            by_kind[PlanConstraintKind.OBLIGATE_SEQUENCE].layer
            == DDICLayer.TESTIMONY
        )
        assert (
            by_kind[PlanConstraintKind.OBLIGATE_SEQUENCE].mode
            == DDICMode.OBLIGATORY
        )
        assert (
            by_kind[PlanConstraintKind.FORBID_AGGREGATE].mode
            == DDICMode.FORBIDDEN
        )
        assert (
            by_kind[PlanConstraintKind.OBLIGATE_WITHIN].mode
            == DDICMode.OBLIGATORY
        )
        # AEGIS-2706 acceptance: require-precondition lives on BELIEF.
        assert (
            by_kind[PlanConstraintKind.REQUIRE_PRECONDITION].layer
            == DDICLayer.BELIEF
        )
        # All four are POSITIVE polarity (negation is via mode, not
        # polarity, for plan-constraints).
        for c in ir.plan_constraints:
            assert c.polarity == DDICPolarity.POSITIVE

    def test_args_term_compiled(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (forbid-aggregate deploy 3)
            """
        )
        ir = compile_meld_module(module)
        c = ir.plan_constraints[0]
        assert c.args == (DDICSymbol("deploy"), DDICInteger(3))

    def test_compound_args_compiled(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (require-precondition deploy (testStatus passed))
            """
        )
        ir = compile_meld_module(module)
        c = ir.plan_constraints[0]
        assert isinstance(c.args[1], DDICCompound)
        assert c.args[1].head == "testStatus"
        assert c.args[1].args == (DDICSymbol("passed"),)

    def test_source_ref_preserved(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (obligate-sequence a b)
            """,
            file="domain.meld",
        )
        ir = compile_meld_module(module)
        assert ir.plan_constraints[0].source_ref.startswith("domain.meld:")

    def test_constraint_ids_unique(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (obligate-sequence a b)
            (obligate-sequence c d)
            (obligate-sequence e f)
            """
        )
        ir = compile_meld_module(module)
        ids = [c.constraint_id for c in ir.plan_constraints]
        assert len(ids) == len(set(ids))


# ── 3. Coexistence with regular v2 statements ─────────────────────


class TestCoexistence:
    def test_plan_constraints_alongside_formulas(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (testimony-obligatory opsAgent runTests Top t0)
            (obligate-sequence runTests deploy)
            """
        )
        ir = compile_meld_module(module)
        assert len(ir.formulas) == 1
        assert len(ir.plan_constraints) == 1

    def test_module_without_plan_constraints_unchanged(self) -> None:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (testimony-obligatory opsAgent runTests Top t0)
            """
        )
        ir = compile_meld_module(module)
        assert ir.plan_constraints == ()


# ── 4. v1 ↔ v2 parity ──────────────────────────────────────────────


class TestV1V2Parity:
    """AEGIS-2706 acceptance: a v1 PlanNormFrame and a v2
    PlanConstraintStatement with the same predicate + args produce
    structurally identical DDICPlanConstraints (modulo
    constraint_id / source_ref). The IR is the single source of
    truth — both load paths converge."""

    def _v1_module_constraint(self) -> object:
        frame = PlanNormFrame(
            predicate="forbidAggregate",
            args=("deploy", 3),
            source="v1.meld:1",
        )
        return compile_plan_constraints_to_module([frame])[0]

    def _v2_module_constraint(self) -> object:
        module = _module(
            """
            (aegis-schema-version 2)
            (case OpsMt)
            (forbid-aggregate deploy 3)
            """,
            file="v2.meld",
        )
        ir = compile_meld_module(module)
        return ir.plan_constraints[0]

    def test_kind_matches(self) -> None:
        assert (
            self._v1_module_constraint().kind  # type: ignore[attr-defined]
            == self._v2_module_constraint().kind  # type: ignore[attr-defined]
        )

    def test_layer_mode_polarity_match(self) -> None:
        v1 = self._v1_module_constraint()
        v2 = self._v2_module_constraint()
        assert v1.layer == v2.layer  # type: ignore[attr-defined]
        assert v1.mode == v2.mode  # type: ignore[attr-defined]
        assert v1.polarity == v2.polarity  # type: ignore[attr-defined]

    def test_args_match(self) -> None:
        v1 = self._v1_module_constraint()
        v2 = self._v2_module_constraint()
        assert v1.args == v2.args  # type: ignore[attr-defined]
