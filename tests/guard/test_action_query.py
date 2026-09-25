"""Tests for the Action → DDIC query-term mapping (AEGIS-2313)."""

from __future__ import annotations

import pytest

from aegis.guard.action import Action
from aegis.guard.action_query import (
    CONTEXT_KEY,
    DEFAULT_CONTEXT,
    DEFAULT_TIME,
    TIME_KEY,
    action_behavior,
    action_context,
    action_time,
)
from aegis.guard.registry import ActionTypeRegistry
from aegis.engine.ddic_ir import DDICCompound, DDICInteger, DDICSymbol
from aegis.kb.knowledge_base import KnowledgeBase


def _empty_registry() -> ActionTypeRegistry:
    kb = KnowledgeBase()
    kb.create_mt("test")
    kb.freeze()
    return ActionTypeRegistry.from_kb(kb)


class TestActionBehavior:
    def test_unknown_action_type_yields_symbol(self) -> None:
        registry = _empty_registry()
        action = Action(action_type="readFile", agent_id="agent-1")
        assert action_behavior(action, registry) == DDICSymbol("readFile")

    def test_action_with_no_schema_parameters_yields_symbol(self) -> None:
        registry = _empty_registry()
        action = Action(
            action_type="readFile",
            agent_id="agent-1",
            proposition={"path": "/etc/passwd"},
        )
        # Empty registry → no schema → bare symbol regardless of proposition.
        assert action_behavior(action, registry) == DDICSymbol("readFile")


class TestActionContext:
    def test_default_when_no_context_key(self) -> None:
        action = Action(action_type="x", agent_id="a")
        assert action_context(action) == DEFAULT_CONTEXT
        assert action_context(action) == DDICSymbol("Top")

    def test_explicit_string_context(self) -> None:
        action = Action(action_type="x", agent_id="a", context={CONTEXT_KEY: "Public"})
        assert action_context(action) == DDICSymbol("Public")

    def test_explicit_compound_context(self) -> None:
        action = Action(
            action_type="x",
            agent_id="a",
            context={CONTEXT_KEY: ("InRole", "Admin")},
        )
        result = action_context(action)
        assert isinstance(result, DDICCompound)
        assert result.head == "InRole"
        assert result.args == (DDICSymbol("Admin"),)


class TestActionTime:
    def test_default_when_no_time_key(self) -> None:
        action = Action(action_type="x", agent_id="a")
        assert action_time(action) == DEFAULT_TIME
        assert action_time(action) == DDICSymbol("tn")

    def test_explicit_string_time(self) -> None:
        action = Action(action_type="x", agent_id="a", context={TIME_KEY: "t5"})
        assert action_time(action) == DDICSymbol("t5")

    def test_explicit_integer_time(self) -> None:
        action = Action(action_type="x", agent_id="a", context={TIME_KEY: 42})
        assert action_time(action) == DDICInteger(42)


class TestKeyConstants:
    def test_keys_are_distinct_and_documented(self) -> None:
        """Reserve-keys must not collide with each other or with common
        proposition fields. AEGIS-2313 #4 replaces the ddic_context shortcut
        with a documented pair of constants."""
        assert CONTEXT_KEY != TIME_KEY
        assert "ddic" in CONTEXT_KEY
        assert "ddic" in TIME_KEY


class TestCompoundLifting:
    def test_compound_term_head_must_be_string(self) -> None:
        from aegis.guard.action_query import _term_from_value

        with pytest.raises(ValueError, match="head must be a string"):
            _term_from_value([42, "x"])

    def test_int_lifts_to_ddic_integer(self) -> None:
        from aegis.guard.action_query import _term_from_value

        assert _term_from_value(7) == DDICInteger(7)

    def test_bool_lifts_to_symbol_not_integer(self) -> None:
        """``True`` / ``False`` are technically int subclasses; we lift
        them as symbols so the rule base sees ``True``/``False`` rather
        than ``1``/``0``."""
        from aegis.guard.action_query import _term_from_value

        assert _term_from_value(True) == DDICSymbol("True")
        assert _term_from_value(False) == DDICSymbol("False")
