"""Tests for audit trail hash-chain integrity verification."""

from __future__ import annotations

import json
from pathlib import Path

from aegis.audit.integrity import verify_integrity
from aegis.audit.trail import AuditTrail
from aegis.guard.action import Action
from aegis.guard.verdict import Decision, ReasonType, Verdict


def _make_action() -> Action:
    return Action(
        action_type="shareIntelligence",
        agent_id="agent-007",
        proposition={"dataClassification": "unclassified"},
    )


def _make_verdict() -> Verdict:
    return Verdict(
        decision=Decision.PERMITTED,
        reason_type=ReasonType.EXPLICIT_NORM,
        justification_chain=("Permitted by norm X",),
        action_type="shareIntelligence",
        agent_id="agent-007",
    )


def _write_n_entries(path: Path, n: int) -> None:
    trail = AuditTrail(path)
    for _ in range(n):
        trail.log(_make_action(), _make_verdict())


class TestVerifyIntegrity:
    def test_valid_chain(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_n_entries(path, 10)

        result = verify_integrity(path)
        assert result.valid
        assert result.total_entries == 10
        assert result.first_entry_id == 0
        assert result.last_entry_id == 9
        assert not result.errors

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = verify_integrity(tmp_path / "nonexistent.jsonl")
        assert not result.valid
        assert result.errors[0].error_type == "FILE_NOT_FOUND"

    def test_modified_entry_detected(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_n_entries(path, 5)

        # Tamper with entry 2
        lines = path.read_text().strip().split("\n")
        data = json.loads(lines[2])
        data["action"]["agent_id"] = "TAMPERED"
        lines[2] = json.dumps(data, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n")

        result = verify_integrity(path)
        assert not result.valid
        assert any(e.error_type == "HASH_MISMATCH" for e in result.errors)

    def test_deleted_entry_detected(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_n_entries(path, 5)

        # Delete entry 2 (middle of chain)
        lines = path.read_text().strip().split("\n")
        del lines[2]
        path.write_text("\n".join(lines) + "\n")

        result = verify_integrity(path)
        assert not result.valid
        # Should detect both sequence gap and hash mismatch
        error_types = {e.error_type for e in result.errors}
        assert "SEQUENCE_GAP" in error_types or "HASH_MISMATCH" in error_types

    def test_inserted_entry_detected(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_n_entries(path, 5)

        # Insert a duplicate of entry 1 after entry 1
        lines = path.read_text().strip().split("\n")
        lines.insert(2, lines[1])
        path.write_text("\n".join(lines) + "\n")

        result = verify_integrity(path)
        assert not result.valid

    def test_corrupt_json_detected(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_n_entries(path, 3)

        lines = path.read_text().strip().split("\n")
        lines[1] = "NOT VALID JSON {{{"
        path.write_text("\n".join(lines) + "\n")

        result = verify_integrity(path)
        assert not result.valid
        assert any(e.error_type == "CORRUPT_JSON" for e in result.errors)

    def test_genesis_mismatch(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_n_entries(path, 1)

        # Tamper with prev_hash of first entry
        lines = path.read_text().strip().split("\n")
        data = json.loads(lines[0])
        data["prev_hash"] = "wrong_hash"
        lines[0] = json.dumps(data, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n")

        result = verify_integrity(path)
        assert not result.valid
        assert any(e.error_type == "GENESIS_MISMATCH" for e in result.errors)

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        path.write_text("")

        result = verify_integrity(path)
        assert result.valid  # empty file = no violations
        assert result.total_entries == 0

    def test_performance_1000_entries(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_n_entries(path, 1000)

        result = verify_integrity(path)
        assert result.valid
        assert result.total_entries == 1000
        assert result.verification_time_ms < 5000  # generous for CI

    def test_verification_time_recorded(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_n_entries(path, 10)

        result = verify_integrity(path)
        assert result.verification_time_ms > 0
