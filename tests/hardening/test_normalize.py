"""Tests for AEGIS-1505: Action Normalization."""

from __future__ import annotations

from aegis.guard.action import Action
from aegis.guard.registry import ActionTypeRegistry
from aegis.hardening.normalize import normalize_action
from aegis.kb.vocabulary_loader import ActionTypeSchema


def _make_registry(action_types: list[str]) -> ActionTypeRegistry:
    registry = ActionTypeRegistry()
    for at in action_types:
        registry._schemas[at] = ActionTypeSchema(name=at, parameters=[], required_context=[])
    return registry


class TestNormalize:
    def test_clean_action_passes(self) -> None:
        action = Action(action_type="shareIntelligence", agent_id="agent-007")
        result = normalize_action(action)
        assert not result.rejected
        assert result.action.action_type == "shareIntelligence"
        assert result.warnings == ()

    def test_strip_action_type_whitespace(self) -> None:
        action = Action(action_type="  shareIntelligence ", agent_id="agent-007")
        result = normalize_action(action)
        assert not result.rejected
        assert result.action.action_type == "shareIntelligence"
        assert len(result.warnings) == 1

    def test_strip_agent_id_whitespace(self) -> None:
        action = Action(action_type="shareIntelligence", agent_id=" agent-007 ")
        result = normalize_action(action)
        assert not result.rejected
        assert result.action.agent_id == "agent-007"
        assert len(result.warnings) == 1

    def test_reject_empty_agent_id(self) -> None:
        action = Action(action_type="shareIntelligence", agent_id="")
        result = normalize_action(action)
        assert result.rejected
        assert "empty" in result.rejection_reason

    def test_reject_whitespace_only_agent_id(self) -> None:
        action = Action(action_type="shareIntelligence", agent_id="   ")
        result = normalize_action(action)
        assert result.rejected
        assert "empty" in result.rejection_reason

    def test_reject_unknown_action_type(self) -> None:
        registry = _make_registry(["shareIntelligence"])
        action = Action(action_type="unknownAction", agent_id="agent-007")
        result = normalize_action(action, registry=registry)
        assert result.rejected
        assert "unknown" in result.rejection_reason

    def test_accept_known_action_type(self) -> None:
        registry = _make_registry(["shareIntelligence"])
        action = Action(action_type="shareIntelligence", agent_id="agent-007")
        result = normalize_action(action, registry=registry)
        assert not result.rejected

    def test_strip_proposition_key_whitespace(self) -> None:
        action = Action(
            action_type="shareIntelligence",
            agent_id="agent-007",
            proposition={" key ": "value"},
        )
        result = normalize_action(action)
        assert not result.rejected
        assert "key" in result.action.proposition
        assert " key " not in result.action.proposition

    def test_reject_non_json_serializable_proposition(self) -> None:
        action = Action(
            action_type="shareIntelligence",
            agent_id="agent-007",
            proposition={"key": object()},
        )
        result = normalize_action(action)
        assert result.rejected
        assert "JSON-serializable" in result.rejection_reason

    def test_valid_json_proposition_values(self) -> None:
        """Various JSON-serializable types should pass."""
        action = Action(
            action_type="shareIntelligence",
            agent_id="agent-007",
            proposition={
                "str": "hello",
                "int": 42,
                "float": 3.14,
                "bool": True,
                "null": None,
                "list": [1, 2, 3],
                "dict": {"nested": "value"},
            },
        )
        result = normalize_action(action)
        assert not result.rejected

    def test_no_registry_skips_action_type_check(self) -> None:
        """Without registry, unknown action types are accepted."""
        action = Action(action_type="anyAction", agent_id="agent-007")
        result = normalize_action(action, registry=None)
        assert not result.rejected
