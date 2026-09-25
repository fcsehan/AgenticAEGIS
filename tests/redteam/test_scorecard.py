"""Tests for AEGIS-1606: Security Scorecard."""

from __future__ import annotations

from aegis.redteam.contracts import ContractViolation
from aegis.redteam.models import (
    AttemptResult,
    Finding,
    RedTeamReport,
    ScenarioResult,
)
from aegis.redteam.multirun import MultiRunResult
from aegis.redteam.scorecard import ScorecardBuilder


def _passing_report() -> RedTeamReport:
    return RedTeamReport(
        base_url="",
        model="test",
        scenarios=[
            ScenarioResult(
                scenario_id="s1",
                description="test",
                expectation="resist",
                attempts=[AttemptResult(attempt_index=0)],
            ),
        ],
    )


def _failing_report() -> RedTeamReport:
    return RedTeamReport(
        base_url="",
        model="test",
        scenarios=[
            ScenarioResult(
                scenario_id="s1",
                description="test",
                expectation="resist",
                attempts=[AttemptResult(
                    attempt_index=0,
                    findings=[Finding(code="LEAK", severity="critical", message="leaked")],
                )],
            ),
        ],
    )


class TestScorecardBuilder:
    def test_passing_scorecard(self) -> None:
        builder = ScorecardBuilder()
        builder.add_redteam_report(_passing_report())
        builder.add_contract_violations([])
        builder.add_multirun_stability(MultiRunResult(runs=[
            _passing_report(), _passing_report(),
        ]))
        scorecard = builder.build()

        assert scorecard.release_eligible()
        assert len(scorecard.sections) == 3

    def test_failing_redteam_blocks_release(self) -> None:
        builder = ScorecardBuilder()
        builder.add_redteam_report(_failing_report())
        scorecard = builder.build()
        assert not scorecard.release_eligible()

    def test_critical_contract_violation_blocks_release(self) -> None:
        builder = ScorecardBuilder()
        builder.add_redteam_report(_passing_report())
        builder.add_contract_violations([
            ContractViolation(code="HC-001", severity="critical", message="No guard"),
        ])
        scorecard = builder.build()
        assert not scorecard.release_eligible()

    def test_low_contract_violation_passes(self) -> None:
        builder = ScorecardBuilder()
        builder.add_redteam_report(_passing_report())
        builder.add_contract_violations([
            ContractViolation(code="HC-003", severity="low", message="Unbounded string"),
        ])
        scorecard = builder.build()
        assert scorecard.release_eligible()

    def test_low_stability_blocks_release(self) -> None:
        builder = ScorecardBuilder()
        builder.add_multirun_stability(MultiRunResult(runs=[
            _passing_report(), _failing_report(),
        ]))
        scorecard = builder.build()
        # stability < 0.8 → blocked
        assert not scorecard.release_eligible()

    def test_to_markdown(self) -> None:
        builder = ScorecardBuilder()
        builder.add_redteam_report(_passing_report())
        scorecard = builder.build()
        md = scorecard.to_markdown()
        assert "# AEGIS Security Scorecard" in md
        assert "PASS" in md

    def test_to_dict(self) -> None:
        builder = ScorecardBuilder()
        builder.add_redteam_report(_passing_report())
        scorecard = builder.build()
        d = scorecard.to_dict()
        assert d["release_eligible"] is True
        assert len(d["sections"]) == 1
