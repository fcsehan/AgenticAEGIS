"""Tests for the intent-action drift reporter (AEGIS-3005, Epic 30)."""

from __future__ import annotations

import json
from pathlib import Path

from aegis.audit.drift_reporter import (
    DriftFinding,
    render_json_report,
    render_text_report,
    scan_audit_log,
)


def _write_audit(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )


def _entry(
    entry_id: int,
    action_type: str,
    user_intent: str | None,
    decision: str = "PERMITTED",
) -> dict:
    action: dict = {
        "action_type": action_type,
        "agent_id": "agent-1",
        "proposition": {},
        "context": {},
    }
    if user_intent is not None:
        action["user_intent"] = user_intent
    return {
        "entry_id": entry_id,
        "event": "ACTION_VERDICT",
        "schema_version": 1,
        "timestamp": f"2026-05-08T10:0{entry_id}:00Z",
        "action": action,
        "verdict": {"decision": decision, "reason_type": "EXPLICIT_NORM"},
        "reasoning_chain": [],
        "domain_versions": {},
        "prev_hash": "x",
        "entry_hash": "y",
    }


class TestNoFindings:
    def test_no_records_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_audit(path, [])
        assert scan_audit_log(path) == []

    def test_records_without_user_intent_are_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_audit(path, [_entry(1, "shareIntelligence", user_intent=None)])
        assert scan_audit_log(path) == []

    def test_overlapping_tokens_skip_finding(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_audit(path, [
            _entry(1, "shareIntelligence", "share the intelligence with HQ"),
        ])
        # "share" and "intelligence" both appear → no drift.
        assert scan_audit_log(path) == []


class TestHighSeverity:
    def test_zero_overlap_is_high_severity(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_audit(path, [
            _entry(1, "deleteIntelligence", "show me the weather forecast"),
        ])
        findings = scan_audit_log(path)
        assert len(findings) == 1
        assert findings[0].severity == "high"
        assert findings[0].action_type == "deleteIntelligence"


class TestMediumSeverity:
    def test_one_token_overlap_with_multi_token_action(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_audit(path, [
            _entry(1, "shareIntelligence", "share something"),  # only "share"
        ])
        findings = scan_audit_log(path)
        assert len(findings) == 1
        assert findings[0].severity == "medium"


class TestSynonymSupport:
    def test_synonyms_reduce_false_positives(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _write_audit(path, [
            _entry(1, "readDiagnosis", "view diagnosis"),
        ])
        # Without synonyms: "read" and "diagnosis" tokens don't overlap
        # A direct diagnosis phrase already overlaps; use a broader synonym
        # to isolate the effect of the configured synonym list:
        _write_audit(path, [
            _entry(2, "readDiagnosis", "show me the data"),
        ])
        without = scan_audit_log(path)
        with_syn = scan_audit_log(
            path,
            synonyms_by_action={"readDiagnosis": ["show me the data", "view"]},
        )
        # Without: "read", "diagnosis" vs "show", "me", "the", "data" → no overlap → high.
        assert len(without) == 1
        assert without[0].severity == "high"
        # With synonym injection: synonym tokens include "show", "me",
        # "the", "data" → overlap → no drift.
        assert with_syn == []


class TestRendering:
    def test_text_report_for_empty_findings(self) -> None:
        assert render_text_report([]) == "No drift findings."

    def test_text_report_includes_header_and_rows(self) -> None:
        findings = [
            DriftFinding(
                entry_id=1, timestamp="t", action_type="A",
                user_intent="x", decision="PERMITTED", severity="high",
            ),
        ]
        out = render_text_report(findings)
        assert "entry_id" in out
        assert "high" in out
        assert "PERMITTED" in out

    def test_text_report_truncates_long_intents(self) -> None:
        long_intent = "x" * 200
        findings = [
            DriftFinding(
                entry_id=1, timestamp="t", action_type="A",
                user_intent=long_intent, decision="PERMITTED", severity="high",
            ),
        ]
        out = render_text_report(findings)
        # Must include the truncation marker, not the full string.
        assert "..." in out
        assert long_intent not in out

    def test_json_report_round_trips(self) -> None:
        findings = [
            DriftFinding(
                entry_id=42, timestamp="t", action_type="A",
                user_intent="x", decision="PERMITTED", severity="high",
            ),
        ]
        parsed = json.loads(render_json_report(findings))
        assert parsed[0]["entry_id"] == 42
        assert parsed[0]["severity"] == "high"


class TestRobustness:
    def test_skips_corrupt_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        path.write_text(
            "not json at all\n"
            + json.dumps(_entry(1, "shareIntelligence", "show me the weather"))
            + "\n",
            encoding="utf-8",
        )
        findings = scan_audit_log(path)
        assert len(findings) == 1
        assert findings[0].entry_id == 1

    def test_skips_non_action_verdict_events(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        record = _entry(1, "share", "no overlap whatsoever foo bar")
        record["event"] = "DOMAIN_RELOAD"
        _write_audit(path, [record])
        assert scan_audit_log(path) == []
