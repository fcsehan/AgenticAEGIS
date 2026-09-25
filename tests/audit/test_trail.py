"""Tests for AuditTrail — hash-chain JSONL writer."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from aegis.audit.integrity import verify_integrity
from aegis.audit.trail import _GENESIS_HASH, AuditTrail
from aegis.errors import AuditWriteError
from aegis.guard.action import Action
from aegis.guard.verdict import Decision, ReasonType, Verdict


def _make_action(**overrides: object) -> Action:
    defaults: dict[str, object] = {
        "action_type": "shareIntelligence",
        "agent_id": "agent-007",
        "proposition": {"dataClassification": "unclassified"},
    }
    defaults.update(overrides)
    return Action(**defaults)  # type: ignore[arg-type]


def _make_verdict(**overrides: object) -> Verdict:
    defaults: dict[str, object] = {
        "decision": Decision.PERMITTED,
        "reason_type": ReasonType.EXPLICIT_NORM,
        "justification_chain": ("Norm X permits",),
        "norms_applied": ("norm-1",),
        "action_type": "shareIntelligence",
        "agent_id": "agent-007",
    }
    defaults.update(overrides)
    return Verdict(**defaults)  # type: ignore[arg-type]


class TestAuditTrail:
    def test_first_entry_uses_genesis_hash(self, tmp_path: Path) -> None:
        trail = AuditTrail(tmp_path / "audit.jsonl")
        entry = trail.log(_make_action(), _make_verdict())
        assert entry.prev_hash == _GENESIS_HASH
        assert entry.entry_id == 0

    def test_hash_chain_integrity(self, tmp_path: Path) -> None:
        trail = AuditTrail(tmp_path / "audit.jsonl")
        e1 = trail.log(_make_action(), _make_verdict())
        e2 = trail.log(_make_action(), _make_verdict())
        e3 = trail.log(_make_action(), _make_verdict())

        assert e2.prev_hash == e1.entry_hash
        assert e3.prev_hash == e2.entry_hash
        assert e1.entry_id == 0
        assert e2.entry_id == 1
        assert e3.entry_id == 2

    def test_jsonl_written(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        trail = AuditTrail(path)
        trail.log(_make_action(), _make_verdict())

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["event"] == "ACTION_VERDICT"
        assert data["schema_version"] == 1
        assert data["entry_id"] == 0

    def test_log_event(self, tmp_path: Path) -> None:
        trail = AuditTrail(tmp_path / "audit.jsonl")
        entry = trail.log_event("DOMAIN_RELOAD", {"reason": "test"})
        assert entry.event == "DOMAIN_RELOAD"
        assert entry.action == {"reason": "test"}
        assert entry.verdict is None

    def test_resume_from_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"

        # Write 3 entries
        trail1 = AuditTrail(path)
        trail1.log(_make_action(), _make_verdict())
        trail1.log(_make_action(), _make_verdict())
        e3 = trail1.log(_make_action(), _make_verdict())

        # Resume
        trail2 = AuditTrail(path)
        e4 = trail2.log(_make_action(), _make_verdict())

        assert e4.entry_id == 3
        assert e4.prev_hash == e3.entry_hash

        # Verify entire chain
        result = verify_integrity(path)
        assert result.valid
        assert result.total_entries == 4

    def test_resume_from_corrupt_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        path.write_text("not valid json\n")

        with pytest.raises(AuditWriteError, match="Cannot resume"):
            AuditTrail(path)

    def test_thread_safety(self, tmp_path: Path) -> None:
        """Concurrent writes produce a valid hash chain."""
        path = tmp_path / "audit.jsonl"
        trail = AuditTrail(path)
        n_threads = 8
        n_per_thread = 50
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for _ in range(n_per_thread):
                    trail.log(_make_action(), _make_verdict())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"

        # Verify chain integrity
        result = verify_integrity(path)
        assert result.valid, f"Integrity errors: {result.errors}"
        assert result.total_entries == n_threads * n_per_thread

    def test_rotation_at_100mb(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        trail = AuditTrail(path)

        # Write one entry
        trail.log(_make_action(), _make_verdict())

        # Simulate file exceeding 100MB
        with patch("aegis.audit.trail._MAX_FILE_SIZE", 1):
            trail.log(_make_action(), _make_verdict())

        # Original file was rotated
        rotated = path.with_suffix(".jsonl.1")
        assert rotated.exists()
        # New file has the second entry
        assert path.exists()

    def test_audit_write_error_on_io_failure(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        trail = AuditTrail(path)

        with (
            patch.object(Path, "open", side_effect=OSError("disk full")),
            pytest.raises(AuditWriteError, match="disk full"),
        ):
            trail.log(_make_action(), _make_verdict())

    def test_entry_contains_action_and_verdict(self, tmp_path: Path) -> None:
        trail = AuditTrail(tmp_path / "audit.jsonl")
        action = _make_action(proposition={"key": "value"})
        verdict = _make_verdict(decision=Decision.FORBIDDEN)
        entry = trail.log(action, verdict)

        assert entry.action is not None
        assert entry.action["action_type"] == "shareIntelligence"
        assert entry.action["proposition"] == {"key": "value"}
        assert entry.verdict is not None
        assert entry.verdict["decision"] == "FORBIDDEN"

    def test_reasoning_chain_from_verdict(self, tmp_path: Path) -> None:
        trail = AuditTrail(tmp_path / "audit.jsonl")
        verdict = _make_verdict(
            justification_chain=("Step 1", "Step 2"),
            norms_applied=("norm-a",),
        )
        entry = trail.log(_make_action(), verdict)
        assert len(entry.reasoning_chain) == 3  # 2 justifications + 1 norm


class TestConfirmationLifecycleLog:
    """AEGIS-3306: log_confirmation captures the full user-confirmation
    lifecycle in a single audit entry."""

    def test_basic_confirmation_record(self, tmp_path: Path) -> None:
        trail = AuditTrail(tmp_path / "audit.jsonl")
        entry = trail.log_confirmation(
            trigger_reasons=["MULTIPLE_MINIMAL_CANDIDATES"],
            echo_format="ACTIVE_RESTATE",
            principal="J2",
            proposed_action_type="readDiagnosis",
            user_intent="show me the diagnosis",
            confirmed=True,
            response_time_ms=4_500,
            final_decision="PERMITTED",
        )
        assert entry.event == "CONFIRMATION_LIFECYCLE"
        assert entry.action is not None
        assert entry.action["principal"] == "J2"
        assert entry.action["confirmed"] is True
        assert entry.action["response_time_ms"] == 4_500
        assert entry.action["final_decision"] == "PERMITTED"
        # Slow response: no fast-confirmation flag.
        assert "fast_confirmation" not in entry.action

    def test_fast_confirmation_is_flagged(self, tmp_path: Path) -> None:
        trail = AuditTrail(tmp_path / "audit.jsonl")
        entry = trail.log_confirmation(
            trigger_reasons=["MULTIPLE_MINIMAL_CANDIDATES"],
            echo_format="PASSIVE_YES_NO",
            principal="J2",
            proposed_action_type="readDiagnosis",
            user_intent="show me the diagnosis",
            confirmed=True,
            response_time_ms=300,  # < 1s = consent-theater suspect
            final_decision="PERMITTED",
        )
        assert entry.action is not None
        assert entry.action["fast_confirmation"] is True

    def test_rejection_path(self, tmp_path: Path) -> None:
        trail = AuditTrail(tmp_path / "audit.jsonl")
        entry = trail.log_confirmation(
            trigger_reasons=["VALIDATOR_DRIFT"],
            echo_format="ACTIVE_RESTATE",
            principal="J2",
            proposed_action_type="deleteIntelligence",
            user_intent="archive the briefing",
            confirmed=False,
            response_time_ms=12_000,
            final_decision="FORBIDDEN",
        )
        assert entry.action is not None
        assert entry.action["confirmed"] is False
        assert entry.action["final_decision"] == "FORBIDDEN"

    def test_lifecycle_is_chained(self, tmp_path: Path) -> None:
        """The lifecycle entry must participate in the hash chain like
        every other event — locking it in via prev_hash."""
        path = tmp_path / "audit.jsonl"
        trail = AuditTrail(path)
        first = trail.log_event("INIT", {"x": 1})
        second = trail.log_confirmation(
            trigger_reasons=["MULTIPLE_MINIMAL_CANDIDATES"],
            echo_format="PASSIVE_YES_NO",
            principal="x",
            proposed_action_type="y",
            user_intent="z",
            confirmed=True,
            response_time_ms=2_000,
            final_decision="PERMITTED",
        )
        assert second.prev_hash == first.entry_hash

    def test_multiple_trigger_reasons_preserved(self, tmp_path: Path) -> None:
        trail = AuditTrail(tmp_path / "audit.jsonl")
        entry = trail.log_confirmation(
            trigger_reasons=["VALIDATOR_DRIFT", "MULTIPLE_MINIMAL_CANDIDATES"],
            echo_format="ACTIVE_RESTATE",
            principal="J2",
            proposed_action_type="x",
            user_intent="y",
            confirmed=True,
            response_time_ms=5_000,
            final_decision="PERMITTED",
        )
        assert entry.action is not None
        assert set(entry.action["trigger_reasons"]) == {
            "VALIDATOR_DRIFT", "MULTIPLE_MINIMAL_CANDIDATES",
        }
