"""AEGIS-1505: Action Normalization.

Normalizes LLM-submitted action fields (whitespace, casing, types)
and rejects malformed input before it reaches the DDIC engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from aegis.guard.action import Action
from aegis.guard.registry import ActionTypeRegistry


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """Outcome of normalizing an :class:`Action`."""

    action: Action
    warnings: tuple[str, ...] = ()
    rejected: bool = False
    rejection_reason: str = ""


def normalize_action(
    action: Action,
    registry: ActionTypeRegistry | None = None,
) -> NormalizationResult:
    """Normalize *action* fields and validate against *registry*.

    Applies:
    - Whitespace stripping on ``action_type``, ``agent_id``, proposition keys
    - Rejection of empty ``agent_id``
    - Rejection of unknown ``action_type`` (when registry provided)
    - Validation that proposition values are JSON-serializable
    """
    warnings: list[str] = []

    # --- Strip whitespace ---
    cleaned_action_type = action.action_type.strip()
    if cleaned_action_type != action.action_type:
        warnings.append(
            f"action_type whitespace stripped: {action.action_type!r} → {cleaned_action_type!r}"
        )

    cleaned_agent_id = action.agent_id.strip()
    if cleaned_agent_id != action.agent_id:
        warnings.append(
            f"agent_id whitespace stripped: {action.agent_id!r} → {cleaned_agent_id!r}"
        )

    # --- Reject empty agent_id ---
    if not cleaned_agent_id:
        return NormalizationResult(
            action=action,
            warnings=tuple(warnings),
            rejected=True,
            rejection_reason="agent_id is empty",
        )

    # --- Clean proposition keys ---
    cleaned_proposition: dict[str, Any] = {}
    for key, value in action.proposition.items():
        stripped_key = key.strip()
        if stripped_key != key:
            warnings.append(
                f"proposition key whitespace stripped: {key!r} → {stripped_key!r}"
            )
        cleaned_proposition[stripped_key] = value

    # --- Validate proposition values are JSON-serializable ---
    for key, value in cleaned_proposition.items():
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            return NormalizationResult(
                action=action,
                warnings=tuple(warnings),
                rejected=True,
                rejection_reason=(
                    f"proposition[{key!r}] is not JSON-serializable: "
                    f"{type(value).__name__}"
                ),
            )

    # --- Reject unknown action_type ---
    if registry is not None and not registry.is_known(cleaned_action_type):
        return NormalizationResult(
            action=action,
            warnings=tuple(warnings),
            rejected=True,
            rejection_reason=f"unknown action_type: {cleaned_action_type!r}",
        )

    # --- Build normalized action ---
    normalized = replace(
        action,
        action_type=cleaned_action_type,
        agent_id=cleaned_agent_id,
        proposition=cleaned_proposition,
    )

    return NormalizationResult(
        action=normalized,
        warnings=tuple(warnings),
    )
