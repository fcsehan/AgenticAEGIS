"""AEGIS-1002: LLM Tool-Use Schema generator.

Generates tool schemas compatible with both Claude Tool Use and
OpenAI Function Calling, automatically derived from the ActionTypeRegistry.

The generated schema ensures the LLM can ONLY propose actions that exist
in the loaded domain — structural enforcement of I5 (Non-Bypassability).
"""

from __future__ import annotations

from typing import Any

from aegis.guard.registry import ActionTypeRegistry


def generate_tool_schema(
    registry: ActionTypeRegistry,
    *,
    include_domain_hints: bool = True,
    require_user_intent: bool = False,
) -> dict[str, Any]:
    """Generate a Claude/OpenAI-compatible tool schema from the registry.

    The schema enumerates all known action types and their parameters,
    ensuring the LLM can only propose actions the Guard can evaluate.

    Args:
        registry: The action type registry (derived from .meld files).
        include_domain_hints: If True, include per-action-type parameter details.
        require_user_intent: If True, ``user_intent`` is added to the
            schema as a *required* field. AEGIS-3004 (Epic 30): the
            LLM must declare its NL interpretation of the user's
            request alongside the formal action. Generic callers
            (microservice / CI) that call ``Guard.check`` directly are
            unaffected because they do not go through this schema —
            ``user_intent`` is enforced at the LLM-tool boundary, not
            at the engine.

    Returns:
        A dict in Claude Tool Use / OpenAI Function Calling format.
    """
    action_types = registry.action_types

    proposition_desc = "Action parameters as key-value pairs."
    if include_domain_hints and action_types:
        hints = _build_parameter_hints(registry)
        if hints:
            proposition_desc += " " + hints

    properties: dict[str, Any] = {
        "action_type": {
            "type": "string",
            "description": "Type of action (domain-specific)",
        },
        "agent_id": {
            "type": "string",
            "description": "Your agent identifier",
        },
        "proposition": {
            "type": "object",
            "description": proposition_desc,
        },
        "context": {
            "type": "object",
            "description": "Additional context (optional)",
        },
    }
    required = ["action_type", "agent_id", "proposition"]

    if require_user_intent:
        properties["user_intent"] = {
            "type": "string",
            "description": (
                "A short natural-language description of what the user "
                "actually wanted. Required so the audit trail records "
                "intent alongside the formal action. Does NOT influence "
                "the verdict — that is purely a function of the action "
                "and the loaded rule base. AEGIS-3004 (Epic 30)."
            ),
        }
        required.append("user_intent")

    schema: dict[str, Any] = {
        "name": "aegis_check",
        "description": (
            "Propose an action to the ethical guard for evaluation. "
            "You MUST call this tool before performing any action. "
            "The guard will respond with PERMITTED, FORBIDDEN, or UNDECIDABLE."
        ),
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }

    # Add enum constraint if action types are known
    if action_types:
        schema["input_schema"]["properties"]["action_type"]["enum"] = action_types

    return schema


def generate_openai_tool(
    registry: ActionTypeRegistry,
    *,
    require_user_intent: bool = False,
) -> dict[str, Any]:
    """Generate an OpenAI-compatible tool definition (wrapped in type+function).

    Per AEGIS-3004: ``require_user_intent`` is forwarded to
    ``generate_tool_schema`` to keep the two surfaces in sync.
    """
    tool_schema = generate_tool_schema(registry, require_user_intent=require_user_intent)
    # OpenAI uses "parameters" instead of "input_schema"
    return {
        "type": "function",
        "function": {
            "name": tool_schema["name"],
            "description": tool_schema["description"],
            "parameters": tool_schema["input_schema"],
        },
    }


class MissingUserIntentError(ValueError):
    """Raised when an LLM tool-call omits ``user_intent`` while the
    orchestrator requires it (AEGIS-3004, Epic 30)."""


def parse_tool_call_arguments(
    args: dict[str, Any],
    *,
    require_user_intent: bool = False,
) -> dict[str, Any]:
    """Validate the arguments of an ``aegis_check`` tool-call.

    Used by the orchestrator path to enforce schema compliance *before*
    the Action object is constructed. Returns the validated kwargs
    dict that ``Action(**parse_tool_call_arguments(...))`` consumes.

    Raises:
        MissingUserIntentError: When ``require_user_intent`` is True and
            the tool-call did not declare ``user_intent``. Generic
            callers that bypass this helper (microservice, CI) are
            unaffected — they may construct Actions without an intent.
    """
    if require_user_intent and not args.get("user_intent"):
        raise MissingUserIntentError(
            "aegis_check tool-call is missing required 'user_intent'. "
            "Declare a short NL description of what the user wanted "
            "alongside the formal action.",
        )
    return args


def format_verdict_for_tool_result(
    decision: str,
    explanation: str,
    executed: bool,
    *,
    reasoning_chain: list[str] | None = None,
    suggestion: str | None = None,
) -> dict[str, Any]:
    """Format a Guard verdict as a tool result for the LLM.

    This is what gets sent back to the LLM as the tool call result.
    """
    result: dict[str, Any] = {
        "decision": decision,
        "explanation": explanation,
        "executed": executed,
    }
    if reasoning_chain:
        result["reasoning_chain"] = reasoning_chain
    if suggestion:
        result["suggestion"] = suggestion
    return result


def _build_parameter_hints(registry: ActionTypeRegistry) -> str:
    """Build human-readable parameter hints for the proposition field."""
    hints: list[str] = []
    for at_name in registry.action_types:
        schema = registry.get_schema(at_name)
        if schema and schema.parameters:
            param_strs = [
                f"{p.name} ({p.type_name})" for p in schema.parameters
            ]
            hints.append(f"For '{at_name}': {', '.join(param_strs)}.")
    return " ".join(hints)
