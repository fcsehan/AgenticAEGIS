"""Tests for AEGIS-1002: LLM Tool-Use Schema generation."""

from __future__ import annotations

import pytest

from aegis.api.tool_schema import (
    MissingUserIntentError,
    format_verdict_for_tool_result,
    generate_openai_tool,
    generate_tool_schema,
    parse_tool_call_arguments,
)
from aegis.guard.registry import ActionTypeRegistry
from aegis.kb.vocabulary_loader import ActionParameter, ActionTypeSchema


def _make_registry(*action_types: str) -> ActionTypeRegistry:
    """Build a registry with given action types (no KB needed)."""
    registry = ActionTypeRegistry()
    for at in action_types:
        registry._schemas[at] = ActionTypeSchema(name=at)
    return registry


def _make_registry_with_params() -> ActionTypeRegistry:
    """Build a registry with action types that have parameters."""
    registry = ActionTypeRegistry()
    registry._schemas["shareIntelligence"] = ActionTypeSchema(
        name="shareIntelligence",
        parameters=[
            ActionParameter(name="dataClassification", type_name="string"),
            ActionParameter(name="recipient", type_name="string"),
        ],
    )
    registry._schemas["deleteIntelligence"] = ActionTypeSchema(
        name="deleteIntelligence",
    )
    return registry


class TestGenerateToolSchema:
    def test_basic_structure(self) -> None:
        schema = generate_tool_schema(_make_registry("shareIntelligence"))
        assert schema["name"] == "aegis_check"
        assert "MUST call this tool" in schema["description"]
        assert "input_schema" in schema

    def test_required_fields(self) -> None:
        schema = generate_tool_schema(_make_registry())
        required = schema["input_schema"]["required"]
        assert "action_type" in required
        assert "agent_id" in required
        assert "proposition" in required

    def test_action_type_enum(self) -> None:
        schema = generate_tool_schema(
            _make_registry("shareIntelligence", "deleteIntelligence")
        )
        enum = schema["input_schema"]["properties"]["action_type"]["enum"]
        assert "shareIntelligence" in enum
        assert "deleteIntelligence" in enum

    def test_no_enum_for_empty_registry(self) -> None:
        schema = generate_tool_schema(_make_registry())
        assert "enum" not in schema["input_schema"]["properties"]["action_type"]

    def test_parameter_hints_in_proposition(self) -> None:
        schema = generate_tool_schema(_make_registry_with_params())
        prop_desc = schema["input_schema"]["properties"]["proposition"]["description"]
        assert "dataClassification" in prop_desc
        assert "shareIntelligence" in prop_desc

    def test_no_hints_when_disabled(self) -> None:
        schema = generate_tool_schema(
            _make_registry_with_params(), include_domain_hints=False
        )
        prop_desc = schema["input_schema"]["properties"]["proposition"]["description"]
        assert "dataClassification" not in prop_desc

    def test_context_field_present(self) -> None:
        schema = generate_tool_schema(_make_registry())
        props = schema["input_schema"]["properties"]
        assert "context" in props


class TestGenerateOpenAITool:
    def test_openai_format(self) -> None:
        tool = generate_openai_tool(_make_registry("shareIntelligence"))
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "aegis_check"
        assert "parameters" in tool["function"]
        # OpenAI uses "parameters", not "input_schema"
        assert "input_schema" not in tool["function"]


class TestFormatVerdictForToolResult:
    def test_basic_format(self) -> None:
        result = format_verdict_for_tool_result(
            decision="PERMITTED",
            explanation="Action allowed",
            executed=True,
        )
        assert result["decision"] == "PERMITTED"
        assert result["executed"] is True

    def test_with_reasoning_chain(self) -> None:
        result = format_verdict_for_tool_result(
            decision="FORBIDDEN",
            explanation="Classified data",
            executed=False,
            reasoning_chain=["Matched norm X", "Decision: FORBIDDEN"],
        )
        assert len(result["reasoning_chain"]) == 2

    def test_with_suggestion(self) -> None:
        result = format_verdict_for_tool_result(
            decision="FORBIDDEN",
            explanation="Not allowed",
            executed=False,
            suggestion="Try an unclassified version",
        )
        assert "suggestion" in result

    def test_no_optional_fields_when_none(self) -> None:
        result = format_verdict_for_tool_result(
            decision="PERMITTED",
            explanation="OK",
            executed=True,
        )
        assert "reasoning_chain" not in result
        assert "suggestion" not in result


class TestUserIntentRequirement:
    """AEGIS-3004 (Epic 30): require_user_intent flag adds the field
    to the tool schema as required, and parse_tool_call_arguments
    enforces the contract at the LLM-tool boundary."""

    def test_default_schema_does_not_require_user_intent(self) -> None:
        """Generic callers (microservice/CI) bypass this schema; their
        Action calls without user_intent must keep working. Locked in
        by ensuring the default schema does not include the field."""
        schema = generate_tool_schema(_make_registry("share"))
        properties = schema["input_schema"]["properties"]
        assert "user_intent" not in properties
        assert "user_intent" not in schema["input_schema"]["required"]

    def test_required_flag_adds_user_intent_to_properties(self) -> None:
        schema = generate_tool_schema(
            _make_registry("share"), require_user_intent=True,
        )
        properties = schema["input_schema"]["properties"]
        assert "user_intent" in properties
        assert properties["user_intent"]["type"] == "string"
        assert "audit" in properties["user_intent"]["description"].lower()

    def test_required_flag_adds_user_intent_to_required_list(self) -> None:
        schema = generate_tool_schema(
            _make_registry("share"), require_user_intent=True,
        )
        assert "user_intent" in schema["input_schema"]["required"]

    def test_openai_wrapper_propagates_flag(self) -> None:
        tool = generate_openai_tool(
            _make_registry("share"), require_user_intent=True,
        )
        params = tool["function"]["parameters"]
        assert "user_intent" in params["properties"]
        assert "user_intent" in params["required"]

    def test_parse_tool_call_arguments_passes_through_when_intent_present(self) -> None:
        args = {
            "action_type": "share",
            "agent_id": "agent-1",
            "proposition": {},
            "user_intent": "show me the data",
        }
        result = parse_tool_call_arguments(args, require_user_intent=True)
        assert result is args

    def test_parse_tool_call_arguments_raises_when_intent_missing(self) -> None:
        args = {
            "action_type": "share",
            "agent_id": "agent-1",
            "proposition": {},
        }
        with pytest.raises(MissingUserIntentError, match="user_intent"):
            parse_tool_call_arguments(args, require_user_intent=True)

    def test_parse_tool_call_arguments_raises_when_intent_empty_string(self) -> None:
        """An empty string is not a valid intent declaration."""
        args = {
            "action_type": "share",
            "agent_id": "agent-1",
            "proposition": {},
            "user_intent": "",
        }
        with pytest.raises(MissingUserIntentError):
            parse_tool_call_arguments(args, require_user_intent=True)

    def test_parse_tool_call_arguments_passes_through_when_disabled(self) -> None:
        """Default mode: missing intent is fine; generic callers keep
        working through this helper too."""
        args = {
            "action_type": "share",
            "agent_id": "agent-1",
            "proposition": {},
        }
        result = parse_tool_call_arguments(args)
        assert result is args
