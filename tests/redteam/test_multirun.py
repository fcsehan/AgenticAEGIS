"""Tests for AEGIS-1603: Multi-run Stability."""

from __future__ import annotations

from aegis.redteam.models import (
    AttemptResult,
    Finding,
    RedTeamReport,
    ScenarioResult,
)
from aegis.redteam.multirun import MultiRunResult


def _report(scenario_statuses: dict[str, bool]) -> RedTeamReport:
    """Create a report where each scenario either passes or fails."""
    scenarios: list[ScenarioResult] = []
    for sid, passes in scenario_statuses.items():
        findings: list[Finding] = []
        if not passes:
            findings.append(Finding(code="TEST", severity="high", message="fail"))
        scenarios.append(ScenarioResult(
            scenario_id=sid,
            description=f"test {sid}",
            expectation="resist",
            attempts=[AttemptResult(attempt_index=0, findings=findings)],
        ))
    return RedTeamReport(base_url="", model="test", scenarios=scenarios)


class TestMultiRunResult:
    def test_stability_score_all_stable(self) -> None:
        result = MultiRunResult(runs=[
            _report({"s1": True, "s2": True}),
            _report({"s1": True, "s2": True}),
            _report({"s1": True, "s2": True}),
        ])
        assert result.stability_score() == 1.0
        assert result.unstable_scenarios() == []

    def test_stability_score_one_unstable(self) -> None:
        result = MultiRunResult(runs=[
            _report({"s1": True, "s2": True}),
            _report({"s1": True, "s2": False}),
            _report({"s1": True, "s2": True}),
        ])
        assert result.stability_score() == 0.5
        assert result.unstable_scenarios() == ["s2"]

    def test_stability_score_empty(self) -> None:
        result = MultiRunResult(runs=[])
        assert result.stability_score() == 1.0
        assert result.unstable_scenarios() == []

    def test_stability_score_all_unstable(self) -> None:
        result = MultiRunResult(runs=[
            _report({"s1": True, "s2": True}),
            _report({"s1": False, "s2": False}),
        ])
        assert result.stability_score() == 0.0
        assert len(result.unstable_scenarios()) == 2
