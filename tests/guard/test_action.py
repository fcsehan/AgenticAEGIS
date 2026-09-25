"""Tests for Action."""

from __future__ import annotations

from aegis.guard.action import Action


class TestAction:
    def test_to_facts(self) -> None:
        action = Action(
            action_type="shareIntelligence",
            agent_id="agent-007",
            proposition={"dataClassification": "classified"},
        )
        facts = action.to_facts()
        assert ("action", "shareIntelligence", "agent-007") in facts
        assert any(f[0] == "actionField" for f in facts)

    def test_validate_limits_ok(self) -> None:
        action = Action(action_type="share", agent_id="agent")
        assert action.validate_limits() == []

    def test_validate_limits_long_action_type(self) -> None:
        action = Action(action_type="x" * 300, agent_id="agent")
        violations = action.validate_limits()
        assert any("action_type" in v for v in violations)

    def test_validate_limits_too_many_fields(self) -> None:
        big_prop = {f"field_{i}": i for i in range(60)}
        action = Action(action_type="share", agent_id="agent", proposition=big_prop)
        violations = action.validate_limits()
        assert any("fields" in v for v in violations)

    def test_user_intent_default_is_none(self) -> None:
        """AEGIS-3001: user_intent is optional, defaults to None,
        existing call-sites are unaffected."""
        action = Action(action_type="share", agent_id="agent")
        assert action.user_intent is None

    def test_user_intent_can_be_supplied(self) -> None:
        action = Action(
            action_type="readDiagnosis",
            agent_id="agent-1",
            user_intent="show me the diagnosis",
        )
        assert action.user_intent == "show me the diagnosis"

    def test_validate_limits_caps_user_intent_length(self) -> None:
        """AEGIS-3001: very long user_intent strings are rejected so the
        audit record cannot be exploded by a malicious or buggy caller."""
        action = Action(
            action_type="share",
            agent_id="agent",
            user_intent="x" * 3_000,
        )
        violations = action.validate_limits()
        assert any("user_intent" in v for v in violations)

    def test_validate_limits_accepts_user_intent_below_cap(self) -> None:
        action = Action(
            action_type="share",
            agent_id="agent",
            user_intent="x" * 2_000,
        )
        assert action.validate_limits() == []
