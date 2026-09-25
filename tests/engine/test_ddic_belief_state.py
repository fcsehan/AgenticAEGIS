"""Tests for DDIC belief-state extraction and verdict mapping."""

from __future__ import annotations

from aegis.engine.ddic_eval import DDICVerdict, build_belief_state, evaluate_ddic_module
from aegis.engine.ddic_ir import compile_meld_module
from aegis.kb.meld_loader import parse_meld_module


class TestBeliefState:
    def test_build_belief_state_returns_forbidden_for_active_forbidden_belief(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (belief-forbidden AgentA HelpCook Monday tn)
            """,
            file="belief-state-forbidden.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        state = build_belief_state(runtime)

        assert state.verdict == DDICVerdict.FORBIDDEN
        assert len(state.active_beliefs) == 1

    def test_build_belief_state_returns_permitted_for_active_optional_belief(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (belief-optional AgentA ShareWeather Public tn)
            """,
            file="belief-state-permitted.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        state = build_belief_state(runtime)

        assert state.verdict == DDICVerdict.PERMITTED
        assert len(state.active_beliefs) == 1

    def test_build_belief_state_returns_undecidable_for_unresolved_active_conflict(self) -> None:
        module = parse_meld_module(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (belief-obligatory AgentA HelpCook Monday tn)
            (belief-forbidden AgentA HelpCook Monday tn)
            """,
            file="belief-state-undecidable.meld",
        )

        runtime = evaluate_ddic_module(compile_meld_module(module))
        state = build_belief_state(runtime)

        assert state.verdict == DDICVerdict.UNDECIDABLE
        assert len(state.unresolved_conflicts) == 1
