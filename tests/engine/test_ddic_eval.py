"""Tests for initial DDIC rule execution over compiled IR."""

from __future__ import annotations

from aegis.engine.ddic_eval import DerivationOrigin, evaluate_ddic_module
from aegis.engine.ddic_ir import compile_meld_module
from aegis.kb.meld_loader import parse_meld_module


class TestCategoricalDefaults:
    def test_d1a_derives_not_testimony_obligatory_from_testimony_optional(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (testimony-optional AgentA ShareWeather Public t1)
            (default-rule D1a
              (implies
                (testimony-optional ?A ?B ?C ?T)
                (not-testimony-obligatory ?A ?B ?C ?T)))
            """,
            file="d1a.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        derived = [f for f in runtime.inferred_formulas if f.origin == DerivationOrigin.CATEGORICAL_DEFAULT]

        assert len(derived) == 1
        formula = derived[0].formula
        assert formula.layer.value == "testimony"
        assert formula.mode.value == "obligatory"
        assert formula.polarity.value == "negative"

    def test_d1b_derives_not_testimony_forbidden_from_testimony_obligatory(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (testimony-obligatory AgentA WearHelmet OnBike t1)
            (default-rule D1b
              (implies
                (testimony-obligatory ?A ?B ?C ?T)
                (not-testimony-forbidden ?A ?B ?C ?T)))
            """,
            file="d1b.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        derived = [f for f in runtime.inferred_formulas if f.origin == DerivationOrigin.CATEGORICAL_DEFAULT]

        assert len(derived) == 1
        formula = derived[0].formula
        assert formula.layer.value == "testimony"
        assert formula.mode.value == "forbidden"
        assert formula.polarity.value == "negative"
        assert formula.agent.value == "AgentA"
        assert formula.behavior.value == "WearHelmet"

    def test_d1d_derives_not_belief_forbidden_from_belief_obligatory(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (belief-obligatory AgentA WearHelmet OnBike tn)
            (default-rule D1d
              (implies
                (belief-obligatory ?A ?B ?C ?T)
                (not-belief-forbidden ?A ?B ?C ?T)))
            """,
            file="d1d.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        derived = [f for f in runtime.inferred_formulas if f.origin == DerivationOrigin.CATEGORICAL_DEFAULT]

        assert len(derived) == 1
        formula = derived[0].formula
        assert formula.layer.value == "belief"
        assert formula.mode.value == "forbidden"
        assert formula.polarity.value == "negative"

    def test_d1c_derives_not_belief_obligatory_from_belief_optional(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (belief-optional AgentA ShareWeather Public tn)
            (default-rule D1c
              (implies
                (belief-optional ?A ?B ?C ?T)
                (not-belief-obligatory ?A ?B ?C ?T)))
            """,
            file="d1c.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        derived = [f for f in runtime.inferred_formulas if f.origin == DerivationOrigin.CATEGORICAL_DEFAULT]

        assert len(derived) == 1
        formula = derived[0].formula
        assert formula.layer.value == "belief"
        assert formula.mode.value == "obligatory"
        assert formula.polarity.value == "negative"


class TestDefeasibleRules:
    def test_r1_derives_belief_obligatory_via_subsumption_and_time(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (before-or-equal t1 tn)
            (behavior-subsumes WearHelmet WearHeadProtection)
            (context-subsumes OnBikeAtNight OnBike)
            (testimony-obligatory AgentA WearHelmet OnBike t1)
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
            file="r1.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        derived = [f for f in runtime.inferred_formulas if f.origin == DerivationOrigin.DEFEASIBLE_RULE]

        assert len(derived) == 1
        formula = derived[0].formula
        assert formula.layer.value == "belief"
        assert formula.mode.value == "obligatory"
        assert formula.agent.value == "AgentA"
        assert formula.behavior.value == "WearHeadProtection"
        assert formula.context.value == "OnBikeAtNight"
        assert formula.time.value == "tn"

    def test_r2_derives_belief_optional_via_subsumption_and_time(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (before-or-equal t1 tn)
            (behavior-subsumes ShareWeather SharePublicInfo)
            (context-subsumes PublicOnDuty Public)
            (testimony-optional AgentA ShareWeather Public t1)
            (defeasible-rule R2
              :from (testimony-optional ?A ?B ?Phi ?T)
              :to   (belief-optional ?A ?C ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification
                     ((testimony-optional ?A ?Z ?Psi ?Tx)
                      (context-subsumes ?Delta ?Psi)
                      (behavior-subsumes ?B ?Z)
                      (between-inclusive ?T ?Tx ?Tn))
              :defeat-mode complete)
            """,
            file="r2.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        derived = [f for f in runtime.inferred_formulas if f.origin == DerivationOrigin.DEFEASIBLE_RULE]

        assert len(derived) == 1
        formula = derived[0].formula
        assert formula.layer.value == "belief"
        assert formula.mode.value == "optional"
        assert formula.agent.value == "AgentA"
        assert formula.behavior.value == "SharePublicInfo"
        assert formula.context.value == "PublicOnDuty"
        assert formula.time.value == "tn"

    def test_r3_derives_belief_forbidden_via_subsumption_and_time(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (before-or-equal t1 tn)
            (behavior-subsumes HelpCookVegetables HelpCook)
            (context-subsumes MondayMorning Monday)
            (testimony-forbidden AgentA HelpCook Monday t1)
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
            file="r3.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        derived = [f for f in runtime.inferred_formulas if f.origin == DerivationOrigin.DEFEASIBLE_RULE]

        assert len(derived) == 1
        formula = derived[0].formula
        assert formula.layer.value == "belief"
        assert formula.mode.value == "forbidden"
        assert formula.behavior.value == "HelpCookVegetables"
        assert formula.context.value == "MondayMorning"

    def test_r4_derives_belief_not_obligatory_via_subsumption_and_time(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (before-or-equal t1 tn)
            (behavior-subsumes SharePublicSummary ShareSensitiveReport)
            (context-subsumes PressBriefing Operations)
            (not-testimony-obligatory AgentA ShareSensitiveReport Operations t1)
            (defeasible-rule R4
              :from (not-testimony-obligatory ?A ?C ?Phi ?T)
              :to   (not-belief-obligatory ?A ?B ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification
                     ((not-testimony-obligatory ?A ?Z ?Psi ?Tx)
                      (between-inclusive ?T ?Tx ?Tn))
              :defeat-mode partial)
            """,
            file="r4.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        derived = [f for f in runtime.inferred_formulas if f.origin == DerivationOrigin.DEFEASIBLE_RULE]

        assert len(derived) == 1
        formula = derived[0].formula
        assert formula.layer.value == "belief"
        assert formula.mode.value == "obligatory"
        assert formula.polarity.value == "negative"
        assert formula.behavior.value == "SharePublicSummary"
        assert formula.context.value == "PressBriefing"


class TestJustifications:
    def test_runtime_records_justification_for_categorical_default(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (belief-optional AgentA ShareWeather Public tn)
            (default-rule D1c
              (implies
                (belief-optional ?A ?B ?C ?T)
                (not-belief-obligatory ?A ?B ?C ?T)))
            """,
            file="justification-d1c.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))

        assert len(runtime.justifications) == 1
        justification = runtime.justifications[0]
        assert justification.rule_id == "D1c"
        assert len(justification.premises) == 1
        assert justification.premises[0].endswith(":3")

    def test_runtime_records_justification_for_defeasible_rule(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (before-or-equal t1 tn)
            (behavior-subsumes ShareWeather SharePublicInfo)
            (context-subsumes PublicOnDuty Public)
            (testimony-optional AgentA ShareWeather Public t1)
            (defeasible-rule R2
              :from (testimony-optional ?A ?B ?Phi ?T)
              :to   (belief-optional ?A ?C ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification
                     ((testimony-optional ?A ?Z ?Psi ?Tx)
                      (between-inclusive ?T ?Tx ?Tn))
              :defeat-mode complete)
            """,
            file="justification-r2.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))

        assert len(runtime.justifications) == 1
        justification = runtime.justifications[0]
        assert justification.rule_id == "R2"
        assert len(justification.premises) == 1
        assert justification.premises[0].endswith(":6")
        assert justification.conclusion_formula_id.startswith("R2:")
