"""AEGIS-1501: Prompt/Tool-Schema Single Source of Truth.

ActionCatalog ensures that prompt action lists, tool schema enums,
and the ActionTypeRegistry all derive from a single source: the MELD-loaded KB.
"""

from __future__ import annotations

from dataclasses import dataclass

from aegis.guard.registry import ActionTypeRegistry
from aegis.orchestrator.prompts import PromptTemplate


@dataclass(frozen=True, slots=True)
class ActionCatalog:
    """Single source of truth for action names across prompts and schemas.

    Wraps :class:`ActionTypeRegistry` and provides derived views for
    prompt rendering, tool schema generation, and divergence detection.
    """

    registry: ActionTypeRegistry

    def action_names(self) -> list[str]:
        """Return all action names from the registry."""
        return self.registry.action_types

    def prompt_actions_string(self) -> str:
        """Return a comma-separated string for prompt rendering."""
        return ", ".join(self.action_names())

    def tool_schema_enum(self) -> list[str]:
        """Return the action name list suitable for a JSON Schema ``enum``."""
        return self.action_names()

    def validate_prompt(self, template: PromptTemplate) -> list[str]:
        """Detect divergence between a prompt template and the registry.

        Returns a list of human-readable divergence messages (empty = clean).
        """
        errors: list[str] = []
        registry_names = set(self.action_names())
        prompt_names = set(template.available_actions)

        stale = prompt_names - registry_names
        if stale:
            errors.append(
                f"Prompt lists actions not in registry: {sorted(stale)}"
            )

        missing = registry_names - prompt_names
        if missing:
            errors.append(
                f"Registry has actions missing from prompt: {sorted(missing)}"
            )

        return errors
