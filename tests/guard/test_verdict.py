"""Tests for Verdict."""

from __future__ import annotations

from aegis.guard.verdict import Decision, ReasonType, Verdict


class TestVerdict:
    def test_explain(self) -> None:
        v = Verdict(
            decision=Decision.PERMITTED,
            reason_type=ReasonType.EXPLICIT_NORM,
            norms_applied=("rule:1",),
            justification_chain=("Step 1",),
        )
        text = v.explain()
        assert "PERMITTED" in text
        assert "rule:1" in text

    def test_decision_enum(self) -> None:
        assert len(Decision) == 3
        assert Decision.PERMITTED.value == "PERMITTED"
        assert Decision.FORBIDDEN.value == "FORBIDDEN"
        assert Decision.UNDECIDABLE.value == "UNDECIDABLE"

    def test_reason_types(self) -> None:
        # All reason types from D-001/D-004 should exist
        assert ReasonType.EXPLICIT_NORM
        assert ReasonType.CWA_NO_PERMISSION
        assert ReasonType.NO_JURISDICTION
        assert ReasonType.UNRESOLVED_CONFLICT
        assert ReasonType.INTERNAL_ERROR
        assert ReasonType.EVALUATION_TIMEOUT
        assert ReasonType.INVALID_ACTION
        assert ReasonType.MISSING_CONTEXT
