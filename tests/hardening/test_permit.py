"""Tests for AEGIS-1504: Permit Tokens."""

from __future__ import annotations

import time

from aegis.guard.action import Action
from aegis.hardening.permit import PermitStore, canonical_action_hash


def _action(
    action_type: str = "shareIntelligence",
    agent_id: str = "agent-007",
    proposition: dict | None = None,
) -> Action:
    return Action(
        action_type=action_type,
        agent_id=agent_id,
        proposition=proposition or {"dataClassification": "classified"},
    )


class TestPermitToken:
    def test_issue_and_consume(self) -> None:
        store = PermitStore()
        action = _action()
        token = store.issue(action)
        assert token.token_id
        assert not token.consumed

        consumed = store.consume(token.token_id, action)
        assert consumed is not None
        assert consumed.consumed

    def test_single_use(self) -> None:
        """Second consumption must fail."""
        store = PermitStore()
        action = _action()
        token = store.issue(action)

        first = store.consume(token.token_id, action)
        assert first is not None

        second = store.consume(token.token_id, action)
        assert second is None

    def test_wrong_action_fails(self) -> None:
        """Consuming with a different action must fail."""
        store = PermitStore()
        action1 = _action(action_type="shareIntelligence")
        action2 = _action(action_type="deleteIntelligence")

        token = store.issue(action1)
        result = store.consume(token.token_id, action2)
        assert result is None

    def test_ttl_expiry(self) -> None:
        """Expired tokens must not be consumable."""
        store = PermitStore(ttl_seconds=0.01)
        action = _action()
        token = store.issue(action)

        time.sleep(0.05)
        result = store.consume(token.token_id, action)
        assert result is None

    def test_unknown_token_fails(self) -> None:
        store = PermitStore()
        action = _action()
        result = store.consume("nonexistent", action)
        assert result is None

    def test_hash_determinism(self) -> None:
        """Same action should produce same hash."""
        action = _action()
        h1 = canonical_action_hash(action)
        h2 = canonical_action_hash(action)
        assert h1 == h2

    def test_hash_different_for_different_actions(self) -> None:
        action1 = _action(action_type="shareIntelligence")
        action2 = _action(action_type="deleteIntelligence")
        assert canonical_action_hash(action1) != canonical_action_hash(action2)

    def test_hash_proposition_order_independent(self) -> None:
        """Proposition key order should not affect hash."""
        a1 = _action(proposition={"a": 1, "b": 2})
        a2 = _action(proposition={"b": 2, "a": 1})
        assert canonical_action_hash(a1) == canonical_action_hash(a2)

    def test_gc_removes_expired(self) -> None:
        store = PermitStore(ttl_seconds=0.01)
        action = _action()
        store.issue(action)

        time.sleep(0.05)
        # GC runs on next issue
        store.issue(action)
        # Expired token should have been cleaned up
        assert len([t for t in store._tokens.values() if not t.is_expired()]) >= 1
