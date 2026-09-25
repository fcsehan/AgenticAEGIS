"""Tests for DDIC defeat handling and conflict classification."""

from __future__ import annotations

from aegis.engine.ddic_eval import ConflictType, DefeatReason, evaluate_ddic_module
from aegis.engine.ddic_ir import compile_meld_module
from aegis.kb.meld_loader import parse_meld_module


class TestLexPosterior:
    def test_later_inconsistent_testimony_defeats_r1_candidate(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (before t1 t2)
            (before t2 tn)
            (before-or-equal t1 tn)
            (behavior-subsumes HelpCook HelpCook)
            (context-subsumes MondayMorning Monday)
            (testimony-obligatory AgentA HelpCook Monday t1)
            (testimony-forbidden AgentA HelpCook MondayMorning t2)
            (defeasible-rule R1
              :from (testimony-obligatory ?A ?B ?Phi ?T)
              :to   (belief-obligatory ?A ?C ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification
                     ((testimony-obligatory ?A ?Z ?Psi ?Tx)
                      (context-subsumes ?Delta ?Psi)
                      (behavior-subsumes ?B ?Z)
                      (between-inclusive ?T ?Tx ?Tn))
              :defeat-mode complete)
            """,
            file="lex-posterior-r1.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))

        active_beliefs = [d for d in runtime.active_formulas if d.formula.layer.value == "belief"]
        defeated_beliefs = [d for d in runtime.defeated_formulas if d.formula.layer.value == "belief"]

        assert len(active_beliefs) == 0
        assert len(defeated_beliefs) == 1
        assert runtime.defeats[0].reason == DefeatReason.LEX_POSTERIOR

    def test_partial_defeat_keeps_unaffected_r3_path_active(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (before t1 t2)
            (before t2 tn)
            (before-or-equal t1 tn)
            (behavior-subsumes CookVegetables Cook)
            (behavior-subsumes CookPeppers Cook)
            (context-subsumes MondayMorning Monday)
            (testimony-forbidden AgentA Cook Monday t1)
            (testimony-obligatory AgentA CookVegetables MondayMorning t2)
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
            file="partial-defeat-r3.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))

        active_behaviors = {
            d.formula.behavior.value
            for d in runtime.active_formulas
            if d.formula.layer.value == "belief"
        }
        defeated_behaviors = {
            d.formula.behavior.value
            for d in runtime.defeated_formulas
            if d.formula.layer.value == "belief"
        }

        assert "CookVegetables" in defeated_behaviors
        assert "CookPeppers" in active_behaviors
        assert any(defeat.reason == DefeatReason.SPECIFIC_EXCEPTION for defeat in runtime.defeats)


class TestPriorityResolution:
    def test_priority_edge_defeats_lower_priority_conflicting_derivation(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (before-or-equal t1 tn)
            (behavior-subsumes HelpCook HelpCook)
            (context-subsumes Monday Monday)
            (testimony-obligatory AgentA HelpCook Monday t1)
            (testimony-forbidden AgentA HelpCook Monday t1)
            (defeasible-rule Rlow
              :from (testimony-obligatory ?A ?B ?Phi ?T)
              :to   (belief-obligatory ?A ?C ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification
                     ((testimony-obligatory ?A ?Z ?Psi ?Tx))
              :defeat-mode complete)
            (defeasible-rule Rhigh
              :from (testimony-forbidden ?A ?B ?Phi ?T)
              :to   (belief-forbidden ?A ?C ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification
                     ((testimony-forbidden ?A ?Z ?Psi ?Tx))
              :defeat-mode complete)
            (priority Rhigh Rlow)
            """,
            file="priority-defeat.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        active_modes = {
            d.formula.mode.value
            for d in runtime.active_formulas
            if d.formula.layer.value == "belief"
        }
        defeated_modes = {
            d.formula.mode.value
            for d in runtime.defeated_formulas
            if d.formula.layer.value == "belief"
        }

        assert active_modes == {"forbidden"}
        assert "obligatory" in defeated_modes
        assert any(defeat.reason == DefeatReason.PRIORITY for defeat in runtime.defeats)

    def test_transitive_priority_prefers_indirectly_higher_rule(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (before-or-equal t1 tn)
            (behavior-subsumes HelpCook HelpCook)
            (context-subsumes Monday Monday)
            (testimony-obligatory AgentA HelpCook Monday t1)
            (testimony-forbidden AgentA HelpCook Monday t1)
            (defeasible-rule Rlow
              :from (testimony-obligatory ?A ?B ?Phi ?T)
              :to   (belief-obligatory ?A ?C ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification
                     ((testimony-obligatory ?A ?Z ?Psi ?Tx))
              :defeat-mode complete)
            (defeasible-rule Rmid
              :from (testimony-forbidden ?A ?B ?Phi ?T)
              :to   (belief-forbidden ?A ?C ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification
                     ((testimony-forbidden ?A ?Z ?Psi ?Tx))
              :defeat-mode complete)
            (priority Rtop Rmid)
            (priority Rmid Rlow)
            """,
            file="priority-transitive-defeat.meld",
        )

        ir = compile_meld_module(module)
        runtime = evaluate_ddic_module(
            ir.__class__(
                formulas=ir.formulas,
                relations=ir.relations,
                defaults=ir.defaults,
                defeasible_rules=(
                    ir.defeasible_rules[0],
                    ir.defeasible_rules[1],
                ),
                priorities=ir.priorities,
                metadata=ir.metadata,
            )
        )
        active_modes = {
            d.formula.mode.value
            for d in runtime.active_formulas
            if d.formula.layer.value == "belief"
        }

        assert active_modes == {"forbidden"}
        assert any(defeat.reason == DefeatReason.PRIORITY for defeat in runtime.defeats)


class TestConflictClassification:
    def test_direct_conflict_is_reported_for_equivalent_behavior(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (testimony-obligatory AgentA HelpCook Monday t1)
            (testimony-forbidden AgentA HelpCook Monday t2)
            """,
            file="direct-conflict.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))

        assert len(runtime.conflicts) == 1
        assert runtime.conflicts[0].conflict_type == ConflictType.DIRECT

    def test_indirect_conflict_is_reported_for_subsumption(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (behavior-subsumes HelpCookVegetables HelpCook)
            (testimony-obligatory AgentA HelpCook Monday t1)
            (testimony-forbidden AgentA HelpCookVegetables Monday t2)
            """,
            file="indirect-conflict.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))

        assert len(runtime.conflicts) == 1
        assert runtime.conflicts[0].conflict_type == ConflictType.INDIRECT

    def test_intersecting_conflict_is_reported_for_intersection(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (behavior-intersects Cook Help HelpCook)
            (testimony-forbidden AgentA Cook InKitchen t1)
            (testimony-obligatory AgentA Help Top t2)
            """,
            file="intersecting-conflict.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))

        assert len(runtime.conflicts) == 1
        assert runtime.conflicts[0].conflict_type == ConflictType.INTERSECTING
        assert runtime.conflicts[0].shared_behavior is not None
