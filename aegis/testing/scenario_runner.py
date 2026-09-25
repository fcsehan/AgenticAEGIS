"""AEGIS-1102: YAML Scenario Runner.

Reads scenario files and runs them against the Guard, validating
expected decisions, norms, and reasoning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Verdict

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Result of a single scenario step."""

    name: str
    action: Action
    verdict: Verdict
    passed: bool
    failures: list[str] = field(default_factory=list)


@dataclass
class ScenarioResult:
    """Result of running a complete scenario."""

    scenario_id: str
    description: str
    passed: bool
    steps: list[StepResult] = field(default_factory=list)
    error: str | None = None

    def report(self) -> str:
        """Human-readable report of the scenario result."""
        lines = [
            f"{'PASS' if self.passed else 'FAIL'}: {self.description} [{self.scenario_id}]",
        ]
        for step in self.steps:
            status = "PASS" if step.passed else "FAIL"
            lines.append(f"  [{status}] {step.name}")
            lines.append(
                f"    Decision: {step.verdict.decision.value}"
            )
            for f in step.failures:
                lines.append(f"    FAIL: {f}")
        if self.error:
            lines.append(f"  ERROR: {self.error}")
        return "\n".join(lines)


class ScenarioRunner:
    """Runs YAML scenario files against a Guard.

    Usage::

        runner = ScenarioRunner(guard)
        result = runner.run_file(Path("tests/prompts/ia_mission_prompts.yaml"))
    """

    def __init__(self, guard: Guard) -> None:
        self._guard = guard

    def run_file(self, path: Path) -> list[ScenarioResult]:
        """Run all scenarios in a YAML file."""
        with path.open() as f:
            data = yaml.safe_load(f)

        agent_id = data.get("agent_id", "testAgent")
        results: list[ScenarioResult] = []

        for scenario in data.get("scenarios", []):
            result = self._run_scenario(scenario, agent_id)
            results.append(result)

        return results

    def _run_scenario(
        self, scenario: dict[str, Any], default_agent_id: str
    ) -> ScenarioResult:
        """Run a single scenario."""
        scenario_id = scenario.get("id", "unknown")
        description = scenario.get("description", "")

        try:
            if "expected_actions" in scenario:
                return self._run_multi_step(
                    scenario, default_agent_id, scenario_id, description
                )
            return self._run_single_step(
                scenario, default_agent_id, scenario_id, description
            )
        except Exception as e:
            return ScenarioResult(
                scenario_id=scenario_id,
                description=description,
                passed=False,
                error=str(e),
            )

    def _run_single_step(
        self,
        scenario: dict[str, Any],
        default_agent_id: str,
        scenario_id: str,
        description: str,
    ) -> ScenarioResult:
        """Run a scenario with a single expected action."""
        expected = scenario.get("expected_action", {})
        action = Action(
            action_type=expected.get("action_type", ""),
            agent_id=expected.get("agent_id", default_agent_id),
            proposition=expected.get("proposition", {}),
        )

        verdict = self._guard.check(action)
        failures = _check_expectations(
            verdict,
            expected_decision=scenario.get("expected_verdict"),
            norms_contain=scenario.get("norms_contain"),
            norms_not_contain=scenario.get("norms_not_contain"),
            reasoning_contains=scenario.get("reasoning_contains"),
        )

        step = StepResult(
            name=description,
            action=action,
            verdict=verdict,
            passed=not failures,
            failures=failures,
        )

        return ScenarioResult(
            scenario_id=scenario_id,
            description=description,
            passed=step.passed,
            steps=[step],
        )

    def _run_multi_step(
        self,
        scenario: dict[str, Any],
        default_agent_id: str,
        scenario_id: str,
        description: str,
    ) -> ScenarioResult:
        """Run a scenario with multiple expected actions (rejection loop)."""
        steps: list[StepResult] = []
        all_passed = True

        for i, expected in enumerate(scenario["expected_actions"]):
            action = Action(
                action_type=expected.get("action_type", ""),
                agent_id=expected.get("agent_id", default_agent_id),
                proposition=expected.get("proposition", {}),
            )

            verdict = self._guard.check(action)
            failures = _check_expectations(
                verdict,
                expected_decision=expected.get("expected_verdict"),
                norms_contain=expected.get("norms_contain"),
                norms_not_contain=expected.get("norms_not_contain"),
                reasoning_contains=expected.get("reasoning_contains"),
            )

            step = StepResult(
                name=f"Step {i + 1}",
                action=action,
                verdict=verdict,
                passed=not failures,
                failures=failures,
            )
            steps.append(step)
            if failures:
                all_passed = False

        return ScenarioResult(
            scenario_id=scenario_id,
            description=description,
            passed=all_passed,
            steps=steps,
        )


def _check_expectations(
    verdict: Verdict,
    *,
    expected_decision: str | None = None,
    norms_contain: str | None = None,
    norms_not_contain: str | None = None,
    reasoning_contains: str | None = None,
) -> list[str]:
    """Check a verdict against expectations, return list of failures."""
    failures: list[str] = []

    if expected_decision is not None:
        actual = verdict.decision.value
        if actual != expected_decision:
            failures.append(f"Expected {expected_decision}, got {actual}")

    if norms_contain is not None:
        norms_str = " ".join(verdict.norms_applied)
        if norms_contain not in norms_str:
            failures.append(
                f"Expected norms to contain '{norms_contain}', "
                f"got {verdict.norms_applied}"
            )

    if norms_not_contain is not None:
        norms_str = " ".join(verdict.norms_applied)
        if norms_not_contain in norms_str:
            failures.append(
                f"Expected norms NOT to contain '{norms_not_contain}', "
                f"but found it in {verdict.norms_applied}"
            )

    if reasoning_contains is not None:
        chain_str = " ".join(verdict.justification_chain)
        if reasoning_contains.lower() not in chain_str.lower():
            failures.append(
                f"Expected reasoning to contain '{reasoning_contains}', "
                f"got {verdict.justification_chain}"
            )

    return failures
