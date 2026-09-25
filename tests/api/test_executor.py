"""Tests for ActionExecutor — AEGIS-1003.

The critical invariant: execute() ALWAYS calls guard.check() first.
No action executor runs without Guard approval.
"""

from __future__ import annotations

import pytest

from aegis.api.executor import ActionExecutor
from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.inheritance import InheritanceGraph
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.registry import ActionTypeRegistry
from aegis.guard.verdict import Decision
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


def _make_guard() -> Guard:
    kb = KnowledgeBase()
    kb.create_mt("test")
    kb.assert_fact(("isa", "allowed", "MissionActionType"), "test")
    kb.assert_fact(("isa", "blocked", "MissionActionType"), "test")
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    graph = InheritanceGraph(reasoner)
    ddic = DDICEngine(graph)
    registry = ActionTypeRegistry.from_kb(kb)
    norms = [
        NormFrame(
            code="TestCode",
            agent_pattern="agent",
            modality=DeonticModality.PERMITTED,
            proposition=("allowed",),
            source="test:1",
        ),
        NormFrame(
            code="TestCode",
            agent_pattern="agent",
            modality=DeonticModality.FORBIDDEN,
            proposition=("blocked",),
            source="test:2",
        ),
    ]
    return Guard(kb=kb, norms=norms, registry=registry, ddic=ddic)


class TestActionExecutor:
    def test_permitted_action_executes(self) -> None:
        """PERMITTED action → executor runs."""
        guard = _make_guard()
        executor = ActionExecutor(guard)
        executed_actions: list[str] = []

        def do_allowed(action: Action) -> str:
            executed_actions.append(action.action_type)
            return "done"

        executor.register("allowed", do_allowed)

        result = executor.execute(Action("allowed", "agent"))
        assert result.verdict.decision == Decision.PERMITTED
        assert result.executed is True
        assert result.executor_result == "done"
        assert executed_actions == ["allowed"]

    def test_forbidden_action_never_executes(self) -> None:
        """FORBIDDEN action → executor NEVER runs. This is I5."""
        guard = _make_guard()
        executor = ActionExecutor(guard)
        executed_actions: list[str] = []

        def do_blocked(action: Action) -> str:
            executed_actions.append(action.action_type)
            return "should never happen"

        executor.register("blocked", do_blocked)

        result = executor.execute(Action("blocked", "agent"))
        assert result.verdict.decision == Decision.FORBIDDEN
        assert result.executed is False
        assert result.executor_result is None
        assert executed_actions == []  # executor was NEVER called

    def test_undecidable_action_never_executes(self) -> None:
        """UNDECIDABLE action → executor NEVER runs."""
        guard = _make_guard()
        executor = ActionExecutor(guard)
        executed_actions: list[str] = []

        def do_unknown(action: Action) -> str:
            executed_actions.append(action.action_type)
            return "should never happen"

        executor.register("totallyUnknown", do_unknown)

        result = executor.execute(Action("totallyUnknown", "agent"))
        assert result.verdict.decision in (Decision.UNDECIDABLE, Decision.FORBIDDEN)
        assert result.executed is False
        assert executed_actions == []

    def test_executor_exception_caught(self) -> None:
        """Executor exception → caught, not propagated."""
        guard = _make_guard()
        executor = ActionExecutor(guard)

        def bad_executor(action: Action) -> str:
            raise RuntimeError("executor crashed")

        executor.register("allowed", bad_executor)

        result = executor.execute(Action("allowed", "agent"))
        assert result.verdict.decision == Decision.PERMITTED
        assert result.executed is False
        assert result.error is not None
        assert "crashed" in result.error

    def test_no_registered_executor(self) -> None:
        """PERMITTED but no executor registered → not executed."""
        guard = _make_guard()
        executor = ActionExecutor(guard)
        # Don't register any executor

        result = executor.execute(Action("allowed", "agent"))
        assert result.verdict.decision == Decision.PERMITTED
        assert result.executed is False

    def test_execute_from_dict(self) -> None:
        """Execute from raw LLM dict format."""
        guard = _make_guard()
        executor = ActionExecutor(guard)
        executor.register("allowed", lambda a: "ok")

        result = executor.execute_from_dict(
            {
                "action_type": "allowed",
                "agent_id": "agent",
                "proposition": {},
            }
        )
        assert result.verdict.decision == Decision.PERMITTED
        assert result.executed is True

    def test_duplicate_registration_raises(self) -> None:
        guard = _make_guard()
        executor = ActionExecutor(guard)
        executor.register("allowed", lambda a: None)
        with pytest.raises(ValueError, match="already registered"):
            executor.register("allowed", lambda a: None)

    def test_as_tool_generates_schema(self) -> None:
        guard = _make_guard()
        executor = ActionExecutor(guard)
        schema = executor.as_tool()
        assert schema["name"] == "aegis_check"
        assert "action_type" in schema["parameters"]["properties"]
        assert "agent_id" in schema["parameters"]["properties"]

    def test_sub_executor_shares_guard(self) -> None:
        """Sub-executors share the same Guard (same rules)."""
        guard = _make_guard()
        parent = ActionExecutor(guard)
        child = parent.create_sub_executor()

        # Child has the same guard rules
        result = child.execute(Action("blocked", "agent"))
        assert result.verdict.decision == Decision.FORBIDDEN
        assert result.executed is False

    def test_no_bypass_no_skip_no_force(self) -> None:
        """There is no parameter or method to skip the Guard check.

        This is a structural test for I5: the API surface of
        ActionExecutor has no bypass mechanism.
        """
        guard = _make_guard()
        executor = ActionExecutor(guard)

        # No skip/bypass/force parameter in execute()
        import inspect

        sig = inspect.signature(executor.execute)
        param_names = set(sig.parameters.keys())
        assert "skip" not in param_names
        assert "bypass" not in param_names
        assert "force" not in param_names
        assert "force_permit" not in param_names
        assert "no_check" not in param_names

        # No such methods exist
        assert not hasattr(executor, "execute_unchecked")
        assert not hasattr(executor, "bypass")
        assert not hasattr(executor, "skip_guard")
        assert not hasattr(executor, "force_permit")
