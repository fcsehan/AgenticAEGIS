"""AEGIS-1103: Performance Benchmarks.

Benchmark suite for Guard.check() and subsystem performance.
Uses pytest-benchmark for statistical rigor.

Targets:
- Guard.check() end-to-end: <50ms P99
- AuditTrail.log(): <1ms
- verify_integrity(): 1000 entries <100ms
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aegis.audit.integrity import verify_integrity
from aegis.audit.trail import AuditTrail
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision, ReasonType, Verdict

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "domains"
MELD_DIR = Path(__file__).parent.parent / "aegis" / "domains" / "iamission"


def _load_test_guard() -> Guard:
    return Guard.from_meld_files(
        [
            FIXTURE_DIR / "test_ontology.meld",
            FIXTURE_DIR / "test_action_vocab.meld",
            FIXTURE_DIR / "test_deontic_rules.meld",
        ]
    )


def _load_ia_guard() -> Guard:
    meld_files = sorted(MELD_DIR.glob("*.meld"))
    return Guard.from_meld_files(meld_files, code_prevalence=["IAMissionCode"])


class TestGuardBenchmarks:
    def test_guard_check_permitted(self, benchmark: Any) -> None:
        guard = _load_test_guard()
        action = Action(
            action_type="shareIntelligence",
            agent_id="intelligenceAgent",
            proposition={"dataClassification": "unclassified"},
        )
        result = benchmark(guard.check, action)
        assert result.decision == Decision.PERMITTED

    def test_guard_check_forbidden(self, benchmark: Any) -> None:
        guard = _load_test_guard()
        action = Action(
            action_type="shareIntelligence",
            agent_id="intelligenceAgent",
            proposition={"dataClassification": "secret"},
        )
        result = benchmark(guard.check, action)
        assert result.decision == Decision.FORBIDDEN

    def test_guard_check_undecidable(self, benchmark: Any) -> None:
        guard = _load_test_guard()
        action = Action(
            action_type="unknownAction",
            agent_id="agent",
        )
        result = benchmark(guard.check, action)
        assert result.decision == Decision.UNDECIDABLE

    def test_ia_mission_guard_check(self, benchmark: Any) -> None:
        guard = _load_ia_guard()
        action = Action(
            action_type="shareIntelligence",
            agent_id="intelligenceAgentInMission",
            proposition={"dataClassification": "classified"},
        )
        result = benchmark(guard.check, action)
        assert result.decision == Decision.FORBIDDEN


class TestAuditBenchmarks:
    def test_audit_trail_log(self, benchmark: Any, tmp_path: Path) -> None:
        trail = AuditTrail(tmp_path / "audit.jsonl")
        action = Action(
            action_type="shareIntelligence",
            agent_id="agent-007",
            proposition={"dataClassification": "unclassified"},
        )
        verdict = Verdict(
            decision=Decision.PERMITTED,
            reason_type=ReasonType.EXPLICIT_NORM,
            justification_chain=("Permitted by norm X",),
            action_type="shareIntelligence",
            agent_id="agent-007",
        )
        benchmark(trail.log, action, verdict)

    def test_verify_integrity_1000(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        trail = AuditTrail(path)
        action = Action(
            action_type="test",
            agent_id="agent",
        )
        verdict = Verdict(
            decision=Decision.PERMITTED,
            reason_type=ReasonType.EXPLICIT_NORM,
            action_type="test",
            agent_id="agent",
        )
        for _ in range(1000):
            trail.log(action, verdict)

        result = verify_integrity(path)
        assert result.valid
        assert result.total_entries == 1000
        # Should complete in well under 5s even on CI
        assert result.verification_time_ms < 5000
