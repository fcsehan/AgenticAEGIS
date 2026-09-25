"""Tests for AuditEntry and ReasoningStep data model."""

from __future__ import annotations

from aegis.audit.entry import AuditEntry, ReasoningStep


class TestReasoningStep:
    def test_to_dict(self) -> None:
        step = ReasoningStep(
            step_type="NORM_MATCHED",
            description="Matched norm: forbidShareClassified",
            details={"norm_source": "IAMissionDeonticRulesMt"},
        )
        d = step.to_dict()
        assert d["step_type"] == "NORM_MATCHED"
        assert d["description"] == "Matched norm: forbidShareClassified"
        assert d["details"]["norm_source"] == "IAMissionDeonticRulesMt"

    def test_from_dict_roundtrip(self) -> None:
        step = ReasoningStep(
            step_type="DECISION",
            description="Final: FORBIDDEN",
            details={"confidence": 1.0},
        )
        restored = ReasoningStep.from_dict(step.to_dict())
        assert restored == step

    def test_default_details(self) -> None:
        step = ReasoningStep(step_type="FACT_ASSERTED", description="test")
        assert step.details == {}

    def test_frozen(self) -> None:
        step = ReasoningStep(step_type="DECISION", description="test")
        try:
            step.step_type = "OTHER"  # type: ignore[misc]
            raise AssertionError("Should raise")
        except AttributeError:
            pass


class TestAuditEntry:
    def _make_entry(self, **overrides: object) -> AuditEntry:
        defaults: dict[str, object] = {
            "entry_id": 0,
            "event": "ACTION_VERDICT",
            "schema_version": 1,
            "timestamp": "2026-03-20T12:00:00+00:00",
            "action": {"action_type": "test", "agent_id": "a1"},
            "verdict": {"decision": "PERMITTED"},
            "reasoning_chain": (
                ReasoningStep("DECISION", "Permitted"),
            ),
            "domain_versions": {},
            "prev_hash": "abc123",
            "entry_hash": "def456",
        }
        defaults.update(overrides)
        return AuditEntry(**defaults)  # type: ignore[arg-type]

    def test_to_dict_includes_all_fields(self) -> None:
        entry = self._make_entry()
        d = entry.to_dict()
        assert d["entry_id"] == 0
        assert d["event"] == "ACTION_VERDICT"
        assert d["schema_version"] == 1
        assert d["entry_hash"] == "def456"
        assert d["prev_hash"] == "abc123"
        assert len(d["reasoning_chain"]) == 1

    def test_to_hashable_dict_excludes_entry_hash(self) -> None:
        entry = self._make_entry()
        d = entry.to_hashable_dict()
        assert "entry_hash" not in d
        assert "prev_hash" in d

    def test_from_dict_roundtrip(self) -> None:
        entry = self._make_entry()
        restored = AuditEntry.from_dict(entry.to_dict())
        assert restored == entry

    def test_explain_verdict(self) -> None:
        entry = self._make_entry(
            verdict={"decision": "FORBIDDEN", "reason_type": "EXPLICIT_NORM"},
            action={"action_type": "shareIntelligence", "agent_id": "agent-007"},
            reasoning_chain=(
                ReasoningStep("NORM_MATCHED", "Matched forbid rule"),
                ReasoningStep("DECISION", "Final: FORBIDDEN"),
            ),
        )
        text = entry.explain()
        assert "FORBIDDEN" in text
        assert "EXPLICIT_NORM" in text
        assert "shareIntelligence" in text
        assert "NORM_MATCHED" in text
        assert "DECISION" in text

    def test_explain_no_verdict(self) -> None:
        entry = self._make_entry(event="DOMAIN_RELOAD", verdict=None, action=None)
        text = entry.explain()
        assert "DOMAIN_RELOAD" in text

    def test_frozen(self) -> None:
        entry = self._make_entry()
        try:
            entry.entry_id = 99  # type: ignore[misc]
            raise AssertionError("Should raise")
        except AttributeError:
            pass
