"""AEGIS-1602: CI Security Gate.

Provides formal exit-code semantics and JUnit XML reporting
for red-team pipeline integration into CI/CD.

Exit codes:
    0 — all scenarios passed
    1 — at least one security failure
    2 — infrastructure error (endpoint down, no .meld files, etc.)
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from aegis.guard.guard import Guard
from aegis.redteam.models import RedTeamReport
from aegis.redteam.pipeline import OpenAICompatibleLLMClient, RedTeamPipeline
from aegis.redteam.scenario_loader import load_scenario_library
from aegis.redteam.scenarios import build_default_scenarios

logger = logging.getLogger(__name__)


def run_ci_gate(
    *,
    scenarios_dir: Path | None = None,
    domains_dir: Path,
    base_url: str,
    model: str,
    code_prevalence: list[str] | None = None,
    attempts: int | None = None,
    fail_on_boundary: bool = False,
) -> int:
    """Run the red-team CI gate and return an exit code.

    Returns:
        0 if all scenarios passed, 1 if any security failure, 2 on infra error.
    """
    # --- Client availability ---
    client = OpenAICompatibleLLMClient(base_url=base_url, model=model)
    if not client.available():
        logger.error("LLM endpoint not reachable: %s", base_url)
        return 2

    # --- Load .meld files ---
    meld_files = sorted(domains_dir.glob("*.meld"))
    if not meld_files:
        logger.error("No .meld files found in %s", domains_dir)
        return 2

    try:
        guard = Guard.from_meld_files(meld_files, code_prevalence=code_prevalence)
    except Exception:
        logger.exception("Failed to load Guard from .meld files")
        return 2

    # --- Load scenarios ---
    if scenarios_dir is not None:
        try:
            scenarios = load_scenario_library(scenarios_dir)
        except Exception:
            logger.exception("Failed to load scenarios from %s", scenarios_dir)
            return 2
    else:
        scenarios = build_default_scenarios()

    if not scenarios:
        logger.error("No scenarios to run")
        return 2

    # --- Run pipeline ---
    try:
        pipeline = RedTeamPipeline(guard=guard, client=client)
        report = pipeline.run_scenarios(scenarios, attempts=attempts)
    except Exception:
        logger.exception("Pipeline execution failed")
        return 2

    # --- Evaluate result ---
    if not report.passed:
        return 1

    if fail_on_boundary:
        for result in report.scenarios:
            if result.status == "EXPOSED_BOUNDARY":
                return 1

    return 0


def report_to_junit_xml(report: RedTeamReport) -> str:
    """Convert a :class:`RedTeamReport` to JUnit XML format.

    Produces one ``<testsuite>`` with one ``<testcase>`` per scenario.
    Failed scenarios get a ``<failure>`` element.
    """
    suite = ET.Element("testsuite")
    suite.set("name", "aegis-redteam")
    suite.set("tests", str(len(report.scenarios)))

    failures = 0
    for result in report.scenarios:
        tc = ET.SubElement(suite, "testcase")
        tc.set("name", result.scenario_id)
        tc.set("classname", f"aegis.redteam.{result.expectation}")

        if not result.passed:
            failures += 1
            failure = ET.SubElement(tc, "failure")
            failure.set("message", f"status={result.status}")
            # Collect finding summaries
            finding_lines: list[str] = []
            for attempt in result.attempts:
                for finding in attempt.findings:
                    finding_lines.append(
                        f"[{finding.severity}] {finding.code}: {finding.message}"
                    )
            failure.text = "\n".join(finding_lines) if finding_lines else result.status

    suite.set("failures", str(failures))

    return ET.tostring(suite, encoding="unicode", xml_declaration=True)
