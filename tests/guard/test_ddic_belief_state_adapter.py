"""Tests for DDIC v2 belief-state to Verdict adapter."""

from __future__ import annotations

from aegis.engine.ddic_eval import build_belief_state, evaluate_ddic_module
from aegis.engine.ddic_ir import compile_meld_module
from aegis.guard.ddic_belief_state_adapter import verdict_from_belief_state, verdict_from_ddic_runtime
from aegis.guard.verdict import Decision, ReasonType
from aegis.kb.meld_loader import parse_meld_module


class TestDDICV2Adapter:
    def test_runtime_adapter_maps_forbidden_belief_to_forbidden_verdict(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (belief-forbidden AgentA HelpCook Monday tn)
            """,
            file="adapter-forbidden.meld",
        )

        verdict = verdict_from_ddic_runtime(
            evaluate_ddic_module(compile_meld_module(module)),
            action_type="helpCook",
            agent_id="AgentA",
        )

        assert verdict.decision == Decision.FORBIDDEN
        assert verdict.reason_type == ReasonType.EXPLICIT_NORM
        assert verdict.action_type == "helpCook"
        assert verdict.agent_id == "AgentA"

    def test_belief_state_adapter_maps_optional_belief_to_permitted_verdict(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (belief-optional AgentA ShareWeather Public tn)
            """,
            file="adapter-permitted.meld",
        )

        state = build_belief_state(evaluate_ddic_module(compile_meld_module(module)))
        verdict = verdict_from_belief_state(state, action_type="shareWeather", agent_id="AgentA")

        assert verdict.decision == Decision.PERMITTED
        assert verdict.reason_type == ReasonType.EXPLICIT_NORM
        assert verdict.justification_chain

    def test_adapter_maps_unresolved_conflict_to_undecidable_verdict(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (belief-obligatory AgentA HelpCook Monday tn)
            (belief-forbidden AgentA HelpCook Monday tn)
            """,
            file="adapter-undecidable.meld",
        )

        state = build_belief_state(evaluate_ddic_module(compile_meld_module(module)))
        verdict = verdict_from_belief_state(state)

        assert verdict.decision == Decision.UNDECIDABLE
        assert verdict.reason_type == ReasonType.UNRESOLVED_CONFLICT
        assert any(step.startswith("conflict:") for step in verdict.justification_chain)

    def test_lex_posterior_defeat_appears_in_justification_chain(self) -> None:
        """AEGIS-2306 acceptance criterion #6: defeats are part of the
        auditable justification chain, not only a runtime side-log.

        Setup mirrors test_later_inconsistent_testimony_defeats_r1_candidate
        from tests/engine/test_ddic_defeat_conflicts.py: a later forbidden
        testimony defeats an earlier obligatory R1 derivation. The Verdict's
        justification chain must surface that defeat with reason
        ``lex_posterior``.
        """
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
            file="adapter-defeat-chain.meld",
        )

        state = build_belief_state(evaluate_ddic_module(compile_meld_module(module)))
        verdict = verdict_from_belief_state(state, action_type="helpCook", agent_id="AgentA")

        defeat_steps = [s for s in verdict.justification_chain if s.startswith("defeat:")]
        assert defeat_steps, (
            f"expected at least one defeat step, got chain={verdict.justification_chain}"
        )
        assert any("lex_posterior" in step for step in defeat_steps)
        assert any(":complete:" in step for step in defeat_steps)

    def test_priority_defeat_appears_in_justification_chain(self) -> None:
        """AEGIS-2306 #6 also covers priority-driven defeat: the chain must
        identify the defeating rule and mark the defeat as ``priority``."""
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
            file="adapter-priority-chain.meld",
        )

        state = build_belief_state(evaluate_ddic_module(compile_meld_module(module)))
        verdict = verdict_from_belief_state(state, action_type="helpCook", agent_id="AgentA")

        defeat_steps = [s for s in verdict.justification_chain if s.startswith("defeat:")]
        assert defeat_steps
        assert any("priority" in step for step in defeat_steps)
        # The defeating rule id must be referenced explicitly so an auditor
        # can trace which rule won the conflict.
        assert any("Rhigh" in step for step in defeat_steps)

    def test_partial_defeat_is_marked_in_justification_chain(self) -> None:
        """Partial vs complete defeat distinction must be visible in the
        chain, as required by AEGIS-2306 #5: distinguish complete and
        partial defeat."""
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
            file="adapter-partial-defeat-chain.meld",
        )

        state = build_belief_state(evaluate_ddic_module(compile_meld_module(module)))
        verdict = verdict_from_belief_state(state, action_type="cook", agent_id="AgentA")

        defeat_steps = [s for s in verdict.justification_chain if s.startswith("defeat:")]
        assert defeat_steps
        assert any(":partial:" in step for step in defeat_steps)
