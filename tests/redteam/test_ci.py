"""Tests for AEGIS-1602: CI Security Gate."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from aegis.redteam.ci import report_to_junit_xml
from aegis.redteam.models import (
    AttemptResult,
    Finding,
    RedTeamReport,
    ScenarioResult,
)


def _make_report(*, pass_all: bool = True) -> RedTeamReport:
    """Create a minimal report for testing."""
    scenarios = [
        ScenarioResult(
            scenario_id="test_scenario_1",
            description="Test scenario 1",
            expectation="resist",
            attempts=[AttemptResult(
                attempt_index=0,
                findings=[] if pass_all else [
                    Finding(code="CANARY_LEAK", severity="critical", message="Leaked canary")
                ],
            )],
        ),
        ScenarioResult(
            scenario_id="test_scenario_2",
            description="Test scenario 2",
            expectation="boundary",
            attempts=[AttemptResult(attempt_index=0)],
        ),
    ]
    return RedTeamReport(base_url="http://localhost:1234/v1", model="test", scenarios=scenarios)


class TestJUnitXML:
    def test_passing_report(self) -> None:
        report = _make_report(pass_all=True)
        xml_str = report_to_junit_xml(report)
        root = ET.fromstring(xml_str)

        assert root.tag == "testsuite"
        assert root.get("name") == "aegis-redteam"
        assert root.get("tests") == "2"
        assert root.get("failures") == "0"

        testcases = root.findall("testcase")
        assert len(testcases) == 2
        assert testcases[0].get("name") == "test_scenario_1"

    def test_failing_report(self) -> None:
        report = _make_report(pass_all=False)
        xml_str = report_to_junit_xml(report)
        root = ET.fromstring(xml_str)

        assert root.get("failures") == "1"
        failure = root.find(".//failure")
        assert failure is not None
        assert "EXPOSED" in (failure.get("message") or "")

    def test_xml_is_valid(self) -> None:
        report = _make_report()
        xml_str = report_to_junit_xml(report)
        # Should parse without error
        ET.fromstring(xml_str)


class TestExitCodes:
    def test_exit_0_on_pass(self) -> None:
        report = _make_report(pass_all=True)
        assert report.passed

    def test_exit_1_on_fail(self) -> None:
        report = _make_report(pass_all=False)
        assert not report.passed
