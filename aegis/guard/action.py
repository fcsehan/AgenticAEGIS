"""Action — the input to Guard.check().

An Action represents what an LLM agent wants to do.  It carries the
action type, proposition (parameters), agent identity, and optional context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# D-007 limits
_MAX_NESTING_DEPTH = 10
_MAX_PROPOSITION_SIZE = 65_536  # 64 KB
_MAX_FIELDS = 50
_MAX_STRING_LENGTH = 256
_MAX_CONTEXT_SIZE = 65_536  # 64 KB
_MAX_USER_INTENT_LENGTH = 2_000  # AEGIS-3001: cap on declared NL intent (bytes/chars)


@dataclass(frozen=True, slots=True)
class Action:
    """An action proposed by an LLM agent.

    Attributes:
        action_type: The type of action (e.g. ``"shareIntelligence"``).
        agent_id: Identity of the agent proposing this action.
        proposition: Parameters of the action (e.g. ``{"dataClassification": "classified"}``).
        context: External context (from enricher, not LLM). Per D-010.
        user_intent: Optional natural-language description of what the
            user actually wanted, declared by the LLM-side caller
            alongside the formal action. AEGIS-3001 (Epic 30,
            Action-Substitution suite). The Guard does *not* use this
            field for any decision — it is purely audit-side and
            visibility-side. Capped at ``_MAX_USER_INTENT_LENGTH``
            characters by ``validate_limits``.
    """

    action_type: str
    agent_id: str
    proposition: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    user_intent: str | None = None

    def to_facts(self) -> list[tuple[Any, ...]]:
        """Convert this action to assertable facts for the KB/engine.

        Produces tuples suitable for pattern matching against norm propositions.
        """
        facts: list[tuple[Any, ...]] = []

        # Base action fact
        facts.append(("action", self.action_type, self.agent_id))

        # Proposition fields as facts
        for key, value in self.proposition.items():
            if isinstance(value, (tuple, list)):
                facts.append(("actionField", self.action_type, key, *value))
            else:
                facts.append(("actionField", self.action_type, key, value))

        # Context fields as facts
        for key, value in self.context.items():
            if isinstance(value, (tuple, list)):
                facts.append(("contextField", self.action_type, key, *value))
            else:
                facts.append(("contextField", self.action_type, key, value))

        return facts

    def validate_limits(self) -> list[str]:
        """Validate D-007 input limits. Returns list of violation messages."""
        violations: list[str] = []

        if len(self.action_type) > _MAX_STRING_LENGTH:
            violations.append(f"action_type exceeds {_MAX_STRING_LENGTH} chars")

        if len(self.agent_id) > _MAX_STRING_LENGTH:
            violations.append(f"agent_id exceeds {_MAX_STRING_LENGTH} chars")

        if len(self.proposition) > _MAX_FIELDS:
            violations.append(f"proposition has {len(self.proposition)} fields (max {_MAX_FIELDS})")

        if len(self.context) > _MAX_FIELDS:
            violations.append(f"context has {len(self.context)} fields (max {_MAX_FIELDS})")

        # Check nesting depth
        depth = _max_depth(self.proposition)
        if depth > _MAX_NESTING_DEPTH:
            violations.append(f"proposition nesting depth {depth} exceeds {_MAX_NESTING_DEPTH}")

        # AEGIS-3001: cap user_intent length to keep audit records bounded.
        if self.user_intent is not None and len(self.user_intent) > _MAX_USER_INTENT_LENGTH:
            violations.append(
                f"user_intent exceeds {_MAX_USER_INTENT_LENGTH} characters",
            )

        return violations


def _max_depth(obj: Any, current: int = 0) -> int:
    """Compute maximum nesting depth of a dict/list structure."""
    if current > _MAX_NESTING_DEPTH + 1:
        return current  # early exit
    if isinstance(obj, dict):
        if not obj:
            return current + 1
        return max(_max_depth(v, current + 1) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        if not obj:
            return current + 1
        return max(_max_depth(v, current + 1) for v in obj)
    return current
