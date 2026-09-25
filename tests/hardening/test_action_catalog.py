"""Tests for AEGIS-1501: ActionCatalog — SSOT for actions."""

from __future__ import annotations

from aegis.guard.registry import ActionTypeRegistry
from aegis.hardening.action_catalog import ActionCatalog
from aegis.orchestrator.prompts import PromptTemplate


def _make_registry(action_types: list[str]) -> ActionTypeRegistry:
    """Create a minimal registry with the given action types."""
    registry = ActionTypeRegistry()
    from aegis.kb.vocabulary_loader import ActionTypeSchema

    for at in action_types:
        registry._schemas[at] = ActionTypeSchema(name=at, parameters=[], required_context=[])
    return registry


class TestActionCatalog:
    def test_action_names_from_registry(self) -> None:
        registry = _make_registry(["shareIntelligence", "deleteIntelligence"])
        catalog = ActionCatalog(registry=registry)
        assert catalog.action_names() == ["shareIntelligence", "deleteIntelligence"]

    def test_prompt_actions_string(self) -> None:
        registry = _make_registry(["shareIntelligence", "deleteIntelligence"])
        catalog = ActionCatalog(registry=registry)
        assert catalog.prompt_actions_string() == "shareIntelligence, deleteIntelligence"

    def test_tool_schema_enum(self) -> None:
        registry = _make_registry(["shareIntelligence"])
        catalog = ActionCatalog(registry=registry)
        assert catalog.tool_schema_enum() == ["shareIntelligence"]

    def test_ssot_consistency(self) -> None:
        """Prompt actions == tool schema enum == registry.action_types."""
        actions = ["shareIntelligence", "deleteIntelligence", "accessPersonalData"]
        registry = _make_registry(actions)
        catalog = ActionCatalog(registry=registry)

        assert catalog.action_names() == registry.action_types
        assert catalog.tool_schema_enum() == registry.action_types
        assert catalog.prompt_actions_string() == ", ".join(registry.action_types)

    def test_validate_prompt_clean(self) -> None:
        """No divergence when prompt matches registry."""
        registry = _make_registry(["shareIntelligence", "deleteIntelligence"])
        catalog = ActionCatalog(registry=registry)
        template = PromptTemplate(
            domain="test",
            role_description="test",
            available_actions=["shareIntelligence", "deleteIntelligence"],
        )
        assert catalog.validate_prompt(template) == []

    def test_validate_prompt_stale_action(self) -> None:
        """Detect prompt listing an action not in registry."""
        registry = _make_registry(["shareIntelligence"])
        catalog = ActionCatalog(registry=registry)
        template = PromptTemplate(
            domain="test",
            role_description="test",
            available_actions=["shareIntelligence", "obsoleteAction"],
        )
        errors = catalog.validate_prompt(template)
        assert len(errors) == 1
        assert "obsoleteAction" in errors[0]

    def test_validate_prompt_missing_action(self) -> None:
        """Detect registry action missing from prompt."""
        registry = _make_registry(["shareIntelligence", "newAction"])
        catalog = ActionCatalog(registry=registry)
        template = PromptTemplate(
            domain="test",
            role_description="test",
            available_actions=["shareIntelligence"],
        )
        errors = catalog.validate_prompt(template)
        assert len(errors) == 1
        assert "newAction" in errors[0]

    def test_validate_prompt_both_divergences(self) -> None:
        """Detect both stale and missing actions."""
        registry = _make_registry(["shareIntelligence", "newAction"])
        catalog = ActionCatalog(registry=registry)
        template = PromptTemplate(
            domain="test",
            role_description="test",
            available_actions=["shareIntelligence", "staleAction"],
        )
        errors = catalog.validate_prompt(template)
        assert len(errors) == 2
