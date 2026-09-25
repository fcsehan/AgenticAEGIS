"""Tests for AEGIS-1702: Guarded Retrieval Broker."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aegis.guard.action import Action
from aegis.guard.verdict import Decision, ReasonType, Verdict
from aegis.hardening.taint import TaintLevel, TaintTracker
from aegis.ifc.broker import RetrievalBroker
from aegis.redteam.tools import WorkspaceFileRuntime


def _make_verdict(decision: Decision, reason: ReasonType = ReasonType.EXPLICIT_NORM) -> Verdict:
    return Verdict(
        decision=decision,
        reason_type=reason,
        justification_chain=("test",),
        action_type="readDocument",
        agent_id="test-agent",
    )


def _make_file(
    tmpdir: Path,
    path: str,
    content: str,
    classification: str = "secret",
    canary_tokens: tuple[str, ...] = (),
) -> WorkspaceFileRuntime:
    abs_path = tmpdir / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    return WorkspaceFileRuntime(
        relative_path=path,
        absolute_path=abs_path,
        classification=classification,
        description="Test file",
        canary_tokens=canary_tokens,
    )


class TestBrokerRead:
    def test_permitted_returns_full_content(self, tmp_path: Path) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.PERMITTED)

        entry = _make_file(tmp_path, "doc.txt", "Hello World", "public")
        broker = RetrievalBroker(guard)
        result = broker.broker_read("doc.txt", entry, "agent-1")

        assert result.response_mode == "full-content"
        assert result.content == "Hello World"
        assert result.redacted is False
        assert len(result.provenance) == 1
        assert result.provenance[0].classification == "public"

    def test_forbidden_returns_deny(self, tmp_path: Path) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.FORBIDDEN)

        entry = _make_file(tmp_path, "secret.txt", "SECRET CONTENT", "secret", ("CANARY-1",))
        broker = RetrievalBroker(guard)
        result = broker.broker_read("secret.txt", entry, "agent-1")

        assert result.response_mode == "deny"
        assert result.content == ""
        assert result.redacted is True

    def test_undecidable_returns_metadata_only(self, tmp_path: Path) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.UNDECIDABLE, ReasonType.NO_JURISDICTION)

        entry = _make_file(tmp_path, "unknown.txt", "Content", "topSecret")
        broker = RetrievalBroker(guard)
        result = broker.broker_read("unknown.txt", entry, "agent-1")

        assert result.response_mode == "metadata-only"
        assert result.content == ""
        assert result.redacted is True

    def test_taint_tracker_populated_on_permitted(self, tmp_path: Path) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.PERMITTED)
        tracker = TaintTracker()

        entry = _make_file(tmp_path, "doc.txt", "data", "secret", ("CANARY-X",))
        broker = RetrievalBroker(guard, taint_tracker=tracker)
        broker.broker_read("doc.txt", entry, "agent-1")

        assert tracker.is_tainted()
        assert "secret" in tracker.touched_classifications
        assert "doc.txt" in tracker.source_set
        # Canary tokens should be registered as markers
        assert any(m.value == "CANARY-X" for m in tracker.markers)

    def test_taint_tracker_populated_on_deny(self, tmp_path: Path) -> None:
        """Even denied reads register provenance for taint tracking."""
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.FORBIDDEN)
        tracker = TaintTracker()

        entry = _make_file(tmp_path, "classified.txt", "data", "secret", ("CANARY-Y",))
        broker = RetrievalBroker(guard, taint_tracker=tracker)
        broker.broker_read("classified.txt", entry, "agent-1")

        assert tracker.is_tainted()
        assert any(m.value == "CANARY-Y" for m in tracker.markers)

    def test_guard_receives_correct_action(self, tmp_path: Path) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.PERMITTED)

        entry = _make_file(tmp_path, "doc.txt", "data", "secret")
        broker = RetrievalBroker(guard)
        broker.broker_read("doc.txt", entry, "agent-007", purpose="externalBriefing")

        guard.check.assert_called_once()
        action = guard.check.call_args[0][0]
        assert isinstance(action, Action)
        assert action.action_type == "readDocument"
        assert action.agent_id == "agent-007"
        assert action.proposition["sourceClassification"] == "secret"
        assert action.proposition["purpose"] == "externalBriefing"


class TestBrokerSearch:
    def test_excludes_forbidden_files(self, tmp_path: Path) -> None:
        guard = MagicMock()

        # First call FORBIDDEN (secret file), second call PERMITTED (public file)
        guard.check.side_effect = [
            _make_verdict(Decision.FORBIDDEN),
            _make_verdict(Decision.PERMITTED),
        ]

        files = {
            "classified.txt": _make_file(
                tmp_path, "classified.txt", "supply route alpha\nsecret data",
                "secret", ("CANARY-1",),
            ),
            "public.txt": _make_file(
                tmp_path, "public.txt", "supply route bravo\npublic info",
                "public",
            ),
        }

        broker = RetrievalBroker(guard)
        result = broker.broker_search("supply route", files, "agent-1")

        import json
        data = json.loads(result.content)
        assert len(data["matches"]) == 1
        assert data["matches"][0]["path"] == "public.txt"
        assert result.redacted is True  # Some files were excluded
        assert result.response_mode == "redacted-snippet"

    def test_all_public_returns_full_content(self, tmp_path: Path) -> None:
        guard = MagicMock()
        guard.check.return_value = _make_verdict(Decision.PERMITTED)

        files = {
            "a.txt": _make_file(tmp_path, "a.txt", "hello world", "public"),
            "b.txt": _make_file(tmp_path, "b.txt", "hello again", "public"),
        }

        broker = RetrievalBroker(guard)
        result = broker.broker_search("hello", files, "agent-1")

        import json
        data = json.loads(result.content)
        assert len(data["matches"]) == 2
        assert result.response_mode == "full-content"
        assert result.redacted is False

    def test_empty_query_returns_empty(self, tmp_path: Path) -> None:
        guard = MagicMock()
        broker = RetrievalBroker(guard)
        result = broker.broker_search("", {}, "agent-1")
        assert result.content == ""
        assert result.provenance == ()
