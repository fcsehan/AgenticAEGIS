"""Tests for AEGIS-2003 + 2004 release-gate and residual-risk register."""

from __future__ import annotations

import json

from aegis.guard.registry import ActionTypeRegistry
from aegis.ifc.channel_action_mapping import CHANNEL_ACTION_MAPPING
from aegis.ifc.guard_coverage import analyze_guard_coverage
from aegis.ifc.host_contract import IFCContractViolation
from aegis.ifc.release_gate import (
    GateGap,
    GuardClaim,
    evaluate_claim,
)
from aegis.ifc.residual_risk import (
    DEFAULT_REGISTER,
    ResidualRisk,
    ResidualRiskRegister,
)
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader


def _full_registry() -> ActionTypeRegistry:
    """Registry with every action_type the channel mappings reference."""
    kb = KnowledgeBase()
    loader = MeldLoader(kb)
    all_actions = sorted({m.action_type for m in CHANNEL_ACTION_MAPPING})
    body = "\n".join(f"(isa {t} ActionType)" for t in all_actions)
    loader.load_string(
        f"(case TestVocabMt)\n{body}\n",
        file="test.meld",
    )
    kb.freeze()
    return ActionTypeRegistry.from_kb(kb)


class TestResidualRisk:
    def test_initial_register_contains_rr_001_through_005(self) -> None:
        ids = {r.risk_id for r in DEFAULT_REGISTER.risks}
        assert ids == {"RR-001", "RR-002", "RR-003", "RR-004", "RR-005"}

    def test_each_initial_risk_has_compensating_control(self) -> None:
        for r in DEFAULT_REGISTER.risks:
            assert r.compensating_control, r.risk_id

    def test_each_initial_risk_has_status(self) -> None:
        for r in DEFAULT_REGISTER.risks:
            assert r.status in ("open", "accepted", "mitigated")

    def test_lookup_by_id(self) -> None:
        rr1 = DEFAULT_REGISTER.by_id("RR-001")
        assert rr1 is not None
        assert rr1.affected_subsystem == "output_filter"

    def test_lookup_unknown_returns_none(self) -> None:
        assert DEFAULT_REGISTER.by_id("RR-999") is None

    def test_filter_by_status(self) -> None:
        opens = DEFAULT_REGISTER.by_status("open")
        accepted = DEFAULT_REGISTER.by_status("accepted")
        assert all(r.status == "open" for r in opens)
        assert all(r.status == "accepted" for r in accepted)
        assert len(opens) + len(accepted) == len(DEFAULT_REGISTER.risks)

    def test_to_json_roundtrip(self) -> None:
        payload = json.loads(DEFAULT_REGISTER.to_json())
        assert "risks" in payload
        assert len(payload["risks"]) == 5

    def test_register_is_frozen(self) -> None:
        try:
            DEFAULT_REGISTER.risks = ()  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("ResidualRiskRegister must be frozen")


class TestReleaseClaim:
    def test_full_claim_when_everything_clean(self) -> None:
        coverage = analyze_guard_coverage(_full_registry())
        result = evaluate_claim(
            coverage,
            contract_violations=[],
            bypass_count=0,
            residual_register=DEFAULT_REGISTER,
        )
        assert result.claim == GuardClaim.FULL
        assert result.passed is True

    def test_partial_when_coverage_gaps(self) -> None:
        # Empty registry → policy gaps.
        kb = KnowledgeBase()
        kb.freeze()
        coverage = analyze_guard_coverage(ActionTypeRegistry.from_kb(kb))
        result = evaluate_claim(
            coverage,
            contract_violations=[],
            bypass_count=0,
            residual_register=DEFAULT_REGISTER,
        )
        assert result.claim == GuardClaim.PARTIAL
        assert any(g.category == "coverage" for g in result.gaps)

    def test_partial_when_bypass_count_nonzero(self) -> None:
        coverage = analyze_guard_coverage(_full_registry())
        result = evaluate_claim(
            coverage,
            contract_violations=[],
            bypass_count=1,
            residual_register=DEFAULT_REGISTER,
        )
        assert result.claim == GuardClaim.PARTIAL
        assert any(g.category == "bypass" for g in result.gaps)

    def test_partial_when_critical_contract_violation(self) -> None:
        coverage = analyze_guard_coverage(_full_registry())
        violations = [
            IFCContractViolation(
                code="HC-005", severity="critical", message="x",
            ),
        ]
        result = evaluate_claim(
            coverage,
            contract_violations=violations,
            bypass_count=0,
            residual_register=DEFAULT_REGISTER,
        )
        assert result.claim == GuardClaim.PARTIAL
        assert any(g.category == "contracts" for g in result.gaps)

    def test_high_severity_contract_does_not_block_claim(self) -> None:
        coverage = analyze_guard_coverage(_full_registry())
        violations = [
            IFCContractViolation(
                code="HC-007", severity="high", message="x",
            ),
        ]
        result = evaluate_claim(
            coverage,
            contract_violations=violations,
            bypass_count=0,
            residual_register=DEFAULT_REGISTER,
        )
        assert result.claim == GuardClaim.FULL
        assert result.critical_contract_violations == 0

    def test_partial_when_no_register_supplied(self) -> None:
        """Per AEGIS-2003: residual risks must be documented; missing
        register blocks the full claim."""
        coverage = analyze_guard_coverage(_full_registry())
        result = evaluate_claim(
            coverage,
            contract_violations=[],
            bypass_count=0,
            residual_register=None,
        )
        assert result.claim == GuardClaim.PARTIAL
        assert any(g.category == "residual_risk" for g in result.gaps)

    def test_open_risks_counted_in_result(self) -> None:
        coverage = analyze_guard_coverage(_full_registry())
        result = evaluate_claim(
            coverage,
            contract_violations=[],
            bypass_count=0,
            residual_register=DEFAULT_REGISTER,
        )
        # RR-003 and RR-004 are open in the default register.
        assert result.open_residual_risks >= 2


class TestSerialization:
    def test_to_json_round_trip(self) -> None:
        coverage = analyze_guard_coverage(_full_registry())
        result = evaluate_claim(
            coverage,
            contract_violations=[],
            bypass_count=0,
            residual_register=DEFAULT_REGISTER,
        )
        payload = json.loads(result.to_json())
        assert payload["claim"] == "full_guard_coverage"
        assert payload["passed"] is True
        assert "coverage" in payload

    def test_summary_full_claim(self) -> None:
        coverage = analyze_guard_coverage(_full_registry())
        result = evaluate_claim(
            coverage,
            contract_violations=[],
            bypass_count=0,
            residual_register=DEFAULT_REGISTER,
        )
        assert "full_guard_coverage" in result.summary()
        assert "bypass_count=0" in result.summary()

    def test_summary_partial_claim_lists_gaps(self) -> None:
        kb = KnowledgeBase()
        kb.freeze()
        coverage = analyze_guard_coverage(ActionTypeRegistry.from_kb(kb))
        result = evaluate_claim(
            coverage,
            contract_violations=[],
            bypass_count=2,
            residual_register=DEFAULT_REGISTER,
        )
        s = result.summary()
        assert "partial_guard_coverage" in s
        assert "bypass" in s


class TestGateGap:
    def test_gap_is_frozen(self) -> None:
        gap = GateGap(category="coverage", detail="x")
        try:
            gap.category = "changed"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("GateGap must be frozen")


class TestCustomRegister:
    def test_custom_register_with_all_open_still_passes(self) -> None:
        """The gate requires *documentation*, not resolution. A
        register full of `open` risks is still acceptable."""
        register = ResidualRiskRegister(
            risks=(
                ResidualRisk(
                    risk_id="X-1",
                    affected_subsystem="something",
                    rationale="something is broken",
                    status="open",
                    compensating_control="manual review",
                ),
            ),
        )
        coverage = analyze_guard_coverage(_full_registry())
        result = evaluate_claim(
            coverage,
            contract_violations=[],
            bypass_count=0,
            residual_register=register,
        )
        assert result.claim == GuardClaim.FULL
        assert result.open_residual_risks == 1
