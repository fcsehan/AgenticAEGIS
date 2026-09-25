"""Tests for DIP ontology builder — LLM-based ontology derivation.

Uses mock LLM responses to test the ontology building pipeline.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from aegis.dip.models import NormativeStatement
from aegis.dip.ontology_builder import (
    _args_to_ontology,
    _sanitize_symbol,
    build_ontology,
)


# ── Mock helpers ────────────────────────────────────────────────────


def _mock_ontology_response(args: dict[str, Any]) -> dict[str, Any]:
    """Build a mock LLM response with a define_ontology tool call."""
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_0",
                    "type": "function",
                    "function": {
                        "name": "define_ontology",
                        "arguments": json.dumps(args),
                    },
                }],
            },
        }],
    }


def _mock_client(response: dict[str, Any]) -> MagicMock:
    client = MagicMock()
    client.chat = MagicMock(return_value=response)
    return client


# ── _sanitize_symbol ────────────────────────────────────────────────


class TestSanitizeSymbol:
    def test_camel_case(self) -> None:
        assert _sanitize_symbol("data controller") == "dataController"

    def test_preserves_existing_camel(self) -> None:
        assert _sanitize_symbol("dataController") == "dataController"

    def test_plain_role_name(self) -> None:
        assert _sanitize_symbol("controller") == "controller"

    def test_diacritic_normalization(self) -> None:
        # Synthetic code-point fixtures exercise normalization without prose.
        assert _sanitize_symbol("o\u0308") == "o"
        assert _sanitize_symbol("u\u0308") == "u"
        assert _sanitize_symbol("\u00df") == "ss"

    def test_accented_chars(self) -> None:
        assert _sanitize_symbol("e\u0301") == "e"
        assert _sanitize_symbol("n\u0303") == "n"

    def test_non_decomposing_latin_character(self) -> None:
        assert _sanitize_symbol("\u0142") == "l"

    def test_non_latin_removed(self) -> None:
        # CJK and Cyrillic code points are removed rather than transliterated.
        assert _sanitize_symbol("\u51e6") == ""
        assert _sanitize_symbol("\u043a") == ""

    def test_multi_word(self) -> None:
        assert _sanitize_symbol("delete personal data") == "deletePersonalData"

    def test_removes_special_chars(self) -> None:
        assert _sanitize_symbol("share-data!") == "sharedata"

    def test_empty(self) -> None:
        assert _sanitize_symbol("") == ""

    def test_first_char_lowercase(self) -> None:
        assert _sanitize_symbol("DataController") == "dataController"


# ── _args_to_ontology ──────────────────────────────────────────────


class TestArgsToOntology:
    def test_full_ontology(self) -> None:
        args = {
            "roles": [
                {"natural_name": "data controller", "meld_symbol": "dataController", "description": "The entity controlling data"},
                {"natural_name": "data subject", "meld_symbol": "dataSubject"},
            ],
            "actions": [
                {"natural_name": "delete data", "meld_symbol": "deleteData", "parameters": ["dataCategory"]},
                {"natural_name": "process data", "meld_symbol": "processData"},
            ],
            "object_categories": ["personalData", "medicalData"],
            "role_hierarchy": [
                {"child": "dpo", "parent": "dataController"},
            ],
            "codes": ["DataProtection"],
        }
        onto = _args_to_ontology(args)
        assert len(onto.roles) == 2
        assert len(onto.actions) == 2
        assert onto.roles[0].meld_symbol == "dataController"
        assert onto.actions[0].parameters == ("dataCategory",)
        assert onto.data_categories == ("personalData", "medicalData")
        assert onto.role_hierarchy == (("dpo", "dataController"),)
        assert onto.codes == ("DataProtection",)
        assert onto.role_map["data controller"] == "dataController"
        assert onto.action_map["delete data"] == "deleteData"

    def test_empty_codes_gets_default(self) -> None:
        args = {"roles": [], "actions": [], "codes": []}
        onto = _args_to_ontology(args)
        assert onto.codes == ("DefaultCode",)

    def test_sanitizes_symbols(self) -> None:
        args = {
            "roles": [{"natural_name": "controller", "meld_symbol": "controller"}],
            "actions": [{"natural_name": "erasure", "meld_symbol": "erasure"}],
            "codes": ["DataProtection"],
        }
        onto = _args_to_ontology(args)
        assert onto.roles[0].meld_symbol == "controller"
        assert onto.actions[0].meld_symbol == "erasure"

    def test_skips_empty_entries(self) -> None:
        args = {
            "roles": [
                {"natural_name": "controller", "meld_symbol": "controller"},
                {"natural_name": "", "meld_symbol": ""},  # should be skipped
            ],
            "actions": [],
            "codes": ["Code1"],
        }
        onto = _args_to_ontology(args)
        assert len(onto.roles) == 1

    def test_minimal(self) -> None:
        onto = _args_to_ontology({"roles": [], "actions": [], "codes": []})
        assert onto.roles == ()
        assert onto.actions == ()


# ── build_ontology (integration with mock) ──────────────────────────


class TestBuildOntology:
    def _make_statements(self) -> list[NormativeStatement]:
        return [
            NormativeStatement(
                source_article="Art. 17(1)",
                modality="OBLIGATORY",
                subject="data controller",
                action="deletion of personal data",
                confidence=0.9,
            ),
            NormativeStatement(
                source_article="Art. 6(1)",
                modality="FORBIDDEN",
                subject="data controller",
                action="processing without legal basis",
                confidence=0.95,
            ),
            NormativeStatement(
                source_article="Art. 15(1)",
                modality="PERMITTED",
                subject="data subject",
                action="access personal data",
                confidence=0.9,
            ),
        ]

    def test_basic_ontology(self) -> None:
        stmts = self._make_statements()
        response = _mock_ontology_response({
            "roles": [
                {"natural_name": "data controller", "meld_symbol": "dataController"},
                {"natural_name": "data subject", "meld_symbol": "dataSubject"},
            ],
            "actions": [
                {"natural_name": "delete data", "meld_symbol": "deleteData", "parameters": ["dataCategory"]},
                {"natural_name": "process data", "meld_symbol": "processData", "parameters": ["legalBasis"]},
                {"natural_name": "access data", "meld_symbol": "accessData"},
            ],
            "object_categories": ["personalData"],
            "codes": ["DataProtection"],
        })
        client = _mock_client(response)
        onto = build_ontology(stmts, client, domain_context="GDPR data protection")
        assert len(onto.roles) == 2
        assert len(onto.actions) == 3
        assert onto.role_map["data controller"] == "dataController"
        assert client.chat.call_count == 1

    def test_empty_statements(self) -> None:
        client = _mock_client({})
        onto = build_ontology([], client)
        assert onto.roles == ()
        assert client.chat.call_count == 0

    def test_no_tool_call_raises(self) -> None:
        stmts = self._make_statements()
        response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "I cannot determine the ontology.",
                },
            }],
        }
        client = _mock_client(response)
        with pytest.raises(RuntimeError, match="did not produce"):
            build_ontology(stmts, client)

    def test_domain_context_passed(self) -> None:
        stmts = self._make_statements()
        response = _mock_ontology_response({
            "roles": [{"natural_name": "commander", "meld_symbol": "commander"}],
            "actions": [{"natural_name": "share intel", "meld_symbol": "shareIntelligence"}],
            "codes": ["EngagementRules"],
        })
        client = _mock_client(response)
        onto = build_ontology(stmts, client, domain_context="Military engagement rules")
        # Verify domain_context was in the system prompt
        call_args = client.chat.call_args
        messages = call_args[0][0]
        system_msg = messages[0]["content"]
        assert "Military engagement rules" in system_msg


class TestBuildOntologyMultiDomain:
    """Test with statements from different domain types."""

    def test_military_domain(self) -> None:
        stmts = [
            NormativeStatement(source_article="Rule 1", modality="FORBIDDEN", subject="commander", action="engage civilian targets", confidence=0.95),
            NormativeStatement(source_article="Rule 2", modality="OBLIGATORY", subject="operator", action="verify target identification", confidence=0.9),
        ]
        response = _mock_ontology_response({
            "roles": [
                {"natural_name": "commander", "meld_symbol": "commander"},
                {"natural_name": "operator", "meld_symbol": "operator"},
            ],
            "actions": [
                {"natural_name": "engage target", "meld_symbol": "engageTarget"},
                {"natural_name": "verify identification", "meld_symbol": "verifyIdentification"},
            ],
            "codes": ["EngagementRules"],
        })
        client = _mock_client(response)
        onto = build_ontology(stmts, client, domain_context="NATO engagement rules")
        assert onto.codes == ("EngagementRules",)
        assert len(onto.roles) == 2

    def test_corporate_policy(self) -> None:
        stmts = [
            NormativeStatement(source_article="Art. 3(1)", modality="OBLIGATORY", subject="employee", action="classify data", confidence=0.9),
            NormativeStatement(source_article="Art. 6(1)", modality="FORBIDDEN", subject="employee", action="transfer to external systems", confidence=0.95),
        ]
        response = _mock_ontology_response({
            "roles": [{"natural_name": "employee", "meld_symbol": "employee"}],
            "actions": [
                {"natural_name": "classify data", "meld_symbol": "classifyData"},
                {"natural_name": "transfer data", "meld_symbol": "transferData", "parameters": ["destination"]},
            ],
            "object_categories": ["confidentialData", "internalData"],
            "codes": ["CorporatePolicy"],
        })
        client = _mock_client(response)
        onto = build_ontology(stmts, client, domain_context="Corporate data handling policy")
        assert onto.data_categories == ("confidentialData", "internalData")
        assert onto.codes == ("CorporatePolicy",)
