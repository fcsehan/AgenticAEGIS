"""TDD tests for MELD v2-DDIC parsing and AST construction.

These tests intentionally define the target behavior for AEGIS-2301/2302.
They are written before the implementation exists and therefore xfail until
the v2 parser and AST modules are added.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

import pytest


def _require_v2_parser() -> Callable[[str, str], Any]:
    """Return the future v2 parser entry point, or xfail if not implemented."""
    meld_loader = importlib.import_module("aegis.kb.meld_loader")
    parser = getattr(meld_loader, "parse_meld_module", None)
    if parser is None:
        pytest.xfail("AEGIS-2302 not implemented: parse_meld_module() missing")
    return parser


def _require_ast_module() -> Any:
    """Return the future DDIC AST module, or xfail if not implemented."""
    try:
        return importlib.import_module("aegis.deontic.ddic_ast")
    except ModuleNotFoundError:
        pytest.xfail("AEGIS-2302/2303 not implemented: aegis.deontic.ddic_ast missing")


class TestMeldV2ModuleParsing:
    def test_schema_version_2_is_accepted(self) -> None:
        parser = _require_v2_parser()

        module = parser(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (testimony-obligatory AgentA WearHelmet OnBike t1)
            """,
            file="v2-test.meld",
        )

        assert module.schema_version == 2
        assert module.source_path == "v2-test.meld"
        assert len(module.statements) == 2

    def test_statement_order_is_preserved(self) -> None:
        parser = _require_v2_parser()
        ast = _require_ast_module()

        module = parser(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (before t1 t2)
            (testimony-forbidden AgentA HelpCook MondayMorning t2)
            (priority D1b R3)
            """,
            file="order-test.meld",
        )

        assert isinstance(module.statements[0], ast.CaseStatement)
        assert isinstance(module.statements[1], ast.RelationStatement)
        assert isinstance(module.statements[2], ast.NormativeFormulaStatement)
        assert isinstance(module.statements[3], ast.PriorityStatement)


class TestNormativeFormulaAst:
    def test_testimony_formula_builds_typed_ast(self) -> None:
        parser = _require_v2_parser()
        ast = _require_ast_module()

        module = parser(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (testimony-obligatory AgentA WearHelmet OnBike t1)
            """,
            file="formula-test.meld",
        )

        stmt = module.statements[1]
        assert isinstance(stmt, ast.NormativeFormulaStatement)
        assert stmt.formula.layer == ast.NormativeLayer.TESTIMONY
        assert stmt.formula.polarity == ast.FormulaPolarity.POSITIVE
        assert stmt.formula.mode == ast.DeonticMode.OBLIGATORY
        assert stmt.formula.agent == "AgentA"
        assert stmt.formula.behavior == "WearHelmet"
        assert stmt.formula.context == "OnBike"
        assert stmt.formula.time == "t1"
        assert stmt.span.file == "formula-test.meld"
        assert stmt.span.line == 3

    def test_negative_belief_formula_builds_typed_ast(self) -> None:
        parser = _require_v2_parser()
        ast = _require_ast_module()

        module = parser(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (not-belief-forbidden AgentA Cook Top tn)
            """,
            file="negative-formula-test.meld",
        )

        stmt = module.statements[1]
        assert isinstance(stmt, ast.NormativeFormulaStatement)
        assert stmt.formula.layer == ast.NormativeLayer.BELIEF
        assert stmt.formula.polarity == ast.FormulaPolarity.NEGATIVE
        assert stmt.formula.mode == ast.DeonticMode.FORBIDDEN


class TestRelationAst:
    def test_behavior_and_context_relations_are_typed(self) -> None:
        parser = _require_v2_parser()
        ast = _require_ast_module()

        module = parser(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (behavior-subsumes HelpCookVegetables HelpCook)
            (context-intersects Monday Morning MondayMorning)
            """,
            file="relations-test.meld",
        )

        behavior_stmt = module.statements[1]
        context_stmt = module.statements[2]

        assert isinstance(behavior_stmt, ast.RelationStatement)
        assert behavior_stmt.kind == ast.RelationKind.BEHAVIOR_SUBSUMES
        assert behavior_stmt.args == ("HelpCookVegetables", "HelpCook")

        assert isinstance(context_stmt, ast.RelationStatement)
        assert context_stmt.kind == ast.RelationKind.CONTEXT_INTERSECTS
        assert context_stmt.args == ("Monday", "Morning", "MondayMorning")


class TestRuleAst:
    def test_default_rule_is_parsed_into_default_rule_statement(self) -> None:
        parser = _require_v2_parser()
        ast = _require_ast_module()

        module = parser(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (default-rule D1b
              (implies
                (testimony-obligatory ?A ?B ?C ?T)
                (not-testimony-forbidden ?A ?B ?C ?T)))
            """,
            file="default-rule-test.meld",
        )

        stmt = module.statements[1]
        assert isinstance(stmt, ast.DefaultRuleStatement)
        assert stmt.rule_id == "D1b"
        assert stmt.body
        assert stmt.head is not None

    def test_defeasible_rule_parses_keyword_fields(self) -> None:
        parser = _require_v2_parser()
        ast = _require_ast_module()

        module = parser(
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
            file="defeasible-rule-test.meld",
        )

        stmt = module.statements[1]
        assert isinstance(stmt, ast.DefeasibleRuleStatement)
        assert stmt.rule_id == "R3"
        assert stmt.when_conditions
        assert stmt.justification_conditions
        assert stmt.defeat_mode == ast.DefeatMode.PARTIAL

    def test_priority_statement_is_typed(self) -> None:
        parser = _require_v2_parser()
        ast = _require_ast_module()

        module = parser(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (priority D1b R3)
            """,
            file="priority-test.meld",
        )

        stmt = module.statements[1]
        assert isinstance(stmt, ast.PriorityStatement)
        assert stmt.higher == "D1b"
        assert stmt.lower == "R3"


class TestMeldV2FailureModes:
    def test_v2_rule_without_schema_2_is_rejected(self) -> None:
        parser = _require_v2_parser()

        with pytest.raises(Exception):
            parser(
                """
                (aegis-schema-version 1)
                (case OlsonDDICMt)
                (defeasible-rule R1
                  :from (testimony-obligatory ?A ?B ?Phi ?T)
                  :to   (belief-obligatory ?A ?C ?Delta ?Tn)
                  :when ()
                  :justification ())
                """,
                file="invalid-version-test.meld",
            )
