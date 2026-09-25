"""Tests for DIP extractor — LLM-based normative statement extraction.

Uses mock LLM responses to test the extraction pipeline without
requiring a live LLM endpoint.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from aegis.dip.extractor import (
    _args_to_statement,
    _parse_extraction_response,
    extract_statements,
)
from aegis.dip.models import ChunkType, NormativeChunk, NormativeStatement


# ── Mock helpers ────────────────────────────────────────────────────


def _mock_response(*tool_args: dict[str, Any]) -> dict[str, Any]:
    """Build a mock LLM response with tool calls."""
    tool_calls = [
        {
            "id": f"call_{i}",
            "type": "function",
            "function": {
                "name": "extract_normative_statement",
                "arguments": json.dumps(args),
            },
        }
        for i, args in enumerate(tool_args)
    ]
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": tool_calls,
                }
            }
        ]
    }


def _mock_client(*responses: dict[str, Any]) -> MagicMock:
    """Create a mock LLMClient that returns predefined responses."""
    client = MagicMock()
    client.chat = MagicMock(side_effect=list(responses))
    return client


# ── _args_to_statement ──────────────────────────────────────────────


class TestArgsToStatement:
    def test_full_args(self) -> None:
        args = {
            "source_ref": "Art. 17(1)",
            "modality": "OBLIGATORY",
            "subject": "data controller",
            "action": "deletion of personal data",
            "object_description": "upon request",
            "conditions": ["purpose ended", "consent withdrawn"],
            "exceptions": ["Art. 17(3)"],
            "vague_terms": ["without undue delay"],
            "confidence": 0.9,
        }
        stmt = _args_to_statement(args)
        assert stmt.source_article == "Art. 17(1)"
        assert stmt.modality == "OBLIGATORY"
        assert stmt.subject == "data controller"
        assert stmt.action == "deletion of personal data"
        assert stmt.conditions == ("purpose ended", "consent withdrawn")
        assert stmt.exceptions == ("Art. 17(3)",)
        assert stmt.vague_terms == ("without undue delay",)
        assert stmt.confidence == 0.9

    def test_minimal_args(self) -> None:
        args = {
            "source_ref": "Section 5.1",
            "modality": "FORBIDDEN",
            "subject": "user",
            "action": "install software",
            "confidence": 0.8,
        }
        stmt = _args_to_statement(args)
        assert stmt.modality == "FORBIDDEN"
        assert stmt.conditions == ()
        assert stmt.vague_terms == ()

    def test_defaults(self) -> None:
        stmt = _args_to_statement({})
        assert stmt.source_article == ""
        assert stmt.modality == "OBLIGATORY"
        assert stmt.confidence == 1.0


# ── _parse_extraction_response ──────────────────────────────────────


class TestParseExtractionResponse:
    def test_single_statement(self) -> None:
        response = _mock_response({
            "source_ref": "Art. 5(1)",
            "modality": "OBLIGATORY",
            "subject": "controller",
            "action": "process data lawfully",
            "confidence": 0.95,
        })
        stmts = _parse_extraction_response(response)
        assert len(stmts) == 1
        assert stmts[0].modality == "OBLIGATORY"

    def test_multiple_statements(self) -> None:
        response = _mock_response(
            {
                "source_ref": "Art. 6(1)",
                "modality": "FORBIDDEN",
                "subject": "controller",
                "action": "process without legal basis",
                "confidence": 0.9,
            },
            {
                "source_ref": "Art. 6(1)(a)",
                "modality": "PERMITTED",
                "subject": "controller",
                "action": "process data with consent",
                "confidence": 0.95,
            },
        )
        stmts = _parse_extraction_response(response)
        assert len(stmts) == 2
        assert stmts[0].modality == "FORBIDDEN"
        assert stmts[1].modality == "PERMITTED"

    def test_empty_response(self) -> None:
        response = {"choices": [{"message": {"role": "assistant", "content": "No norms found."}}]}
        stmts = _parse_extraction_response(response)
        assert stmts == []

    def test_skips_unknown_tool(self) -> None:
        response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "function": {
                            "name": "unknown_tool",
                            "arguments": "{}",
                        },
                    }],
                },
            }],
        }
        stmts = _parse_extraction_response(response)
        assert stmts == []

    def test_skips_malformed_args(self) -> None:
        response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "function": {
                            "name": "extract_normative_statement",
                            "arguments": "not-valid-json{{{",
                        },
                    }],
                },
            }],
        }
        stmts = _parse_extraction_response(response)
        assert stmts == []


# ── extract_statements (integration with mock) ─────────────────────


class TestExtractStatements:
    def _make_chunks(self) -> list[NormativeChunk]:
        return [
            NormativeChunk(
                article_ref="Art. 5(1)",
                text="Data must be processed lawfully.",
                chunk_type=ChunkType.OBLIGATION,
            ),
            NormativeChunk(
                article_ref="Art. 6(1)",
                text="Processing is only lawful if consent is given.",
                chunk_type=ChunkType.PERMISSION,
            ),
            NormativeChunk(
                article_ref="Art. 9(1)",
                text="Processing of special categories is prohibited.",
                chunk_type=ChunkType.PROHIBITION,
            ),
        ]

    def test_basic_extraction(self) -> None:
        chunks = self._make_chunks()
        response = _mock_response(
            {"source_ref": "Art. 5(1)", "modality": "OBLIGATORY", "subject": "controller", "action": "process lawfully", "confidence": 0.9},
            {"source_ref": "Art. 6(1)", "modality": "PERMITTED", "subject": "controller", "action": "process with consent", "confidence": 0.85},
            {"source_ref": "Art. 9(1)", "modality": "FORBIDDEN", "subject": "controller", "action": "process special categories", "confidence": 0.95},
        )
        client = _mock_client(response)
        stmts = extract_statements(chunks, client)
        assert len(stmts) == 3
        assert client.chat.call_count == 1  # all in one batch

    def test_batch_splitting(self) -> None:
        chunks = self._make_chunks()
        r1 = _mock_response(
            {"source_ref": "Art. 5(1)", "modality": "OBLIGATORY", "subject": "c", "action": "a", "confidence": 0.9},
        )
        r2 = _mock_response(
            {"source_ref": "Art. 6(1)", "modality": "PERMITTED", "subject": "c", "action": "b", "confidence": 0.9},
        )
        r3 = _mock_response(
            {"source_ref": "Art. 9(1)", "modality": "FORBIDDEN", "subject": "c", "action": "c", "confidence": 0.9},
        )
        client = _mock_client(r1, r2, r3)
        stmts = extract_statements(chunks, client, batch_size=1)
        assert len(stmts) == 3
        assert client.chat.call_count == 3

    def test_filters_organizational(self) -> None:
        chunks = [
            NormativeChunk(article_ref="Art. 1", text="Scope.", chunk_type=ChunkType.ORGANIZATIONAL),
            NormativeChunk(article_ref="Art. 5(1)", text="Must do.", chunk_type=ChunkType.OBLIGATION),
        ]
        response = _mock_response(
            {"source_ref": "Art. 5(1)", "modality": "OBLIGATORY", "subject": "c", "action": "a", "confidence": 0.9},
        )
        client = _mock_client(response)
        stmts = extract_statements(chunks, client)
        assert len(stmts) == 1

    def test_filters_definitions(self) -> None:
        chunks = [
            NormativeChunk(article_ref="Art. 4", text="Definitions.", chunk_type=ChunkType.DEFINITION),
        ]
        client = _mock_client()
        stmts = extract_statements(chunks, client)
        assert stmts == []
        assert client.chat.call_count == 0

    def test_empty_chunks(self) -> None:
        client = _mock_client()
        stmts = extract_statements([], client)
        assert stmts == []

    def test_failed_batch_continues(self) -> None:
        chunks = self._make_chunks()
        r_ok = _mock_response(
            {"source_ref": "Art. 5(1)", "modality": "OBLIGATORY", "subject": "c", "action": "a", "confidence": 0.9},
        )
        client = MagicMock()
        client.chat = MagicMock(side_effect=[Exception("API error"), r_ok, r_ok])
        stmts = extract_statements(chunks, client, batch_size=1)
        # First batch fails, second and third succeed
        assert len(stmts) == 2

    def test_progress_callback(self) -> None:
        chunks = self._make_chunks()
        response = _mock_response(
            {"source_ref": "Art. 5(1)", "modality": "OBLIGATORY", "subject": "c", "action": "a", "confidence": 0.9},
        )
        client = _mock_client(response, response)
        progress_calls: list[tuple[int, int, int]] = []
        extract_statements(
            chunks, client, batch_size=2,
            on_progress=lambda b, t, s: progress_calls.append((b, t, s)),
        )
        assert len(progress_calls) == 2  # 2 batches


class TestExtractStatementsEnglish:
    """Test with English policy-style chunks."""

    def test_english_policy(self) -> None:
        chunks = [
            NormativeChunk(
                article_ref="Art. 4(1)",
                text="Employees must not access data beyond their authorization level.",
                chunk_type=ChunkType.PROHIBITION,
            ),
            NormativeChunk(
                article_ref="Art. 5(1)",
                text="Personal data must be deleted within 30 days.",
                chunk_type=ChunkType.OBLIGATION,
            ),
        ]
        response = _mock_response(
            {"source_ref": "Art. 4(1)", "modality": "FORBIDDEN", "subject": "employee", "action": "access data beyond authorization", "confidence": 0.95},
            {"source_ref": "Art. 5(1)", "modality": "OBLIGATORY", "subject": "organization", "action": "delete personal data within 30 days", "confidence": 0.9},
        )
        client = _mock_client(response)
        stmts = extract_statements(chunks, client, domain_context="Corporate data handling policy")
        assert len(stmts) == 2
        assert stmts[0].modality == "FORBIDDEN"
        assert stmts[1].modality == "OBLIGATORY"
