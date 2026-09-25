"""AEGIS-1603: Multi-run Stability.

Runs red-team scenarios multiple times to detect flaky results
caused by LLM non-determinism.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aegis.redteam.models import RedTeamReport, RedTeamScenario
from aegis.redteam.pipeline import RedTeamPipeline


@dataclass
class MultiRunResult:
    """Aggregate result of running scenarios multiple times.

    Attributes:
        runs: Individual :class:`RedTeamReport` per run.
    """

    runs: list[RedTeamReport] = field(default_factory=list)

    def stability_score(self) -> float:
        """Fraction of scenarios that are stable across all runs.

        A scenario is stable if its status is the same in every run.
        Returns 1.0 if all scenarios are stable, 0.0 if none are.
        """
        if not self.runs:
            return 1.0

        # Collect scenario IDs from the first run
        scenario_ids = [r.scenario_id for r in self.runs[0].scenarios]
        if not scenario_ids:
            return 1.0

        stable_count = 0
        for sid in scenario_ids:
            statuses: set[str] = set()
            for run in self.runs:
                for result in run.scenarios:
                    if result.scenario_id == sid:
                        statuses.add(result.status)
                        break
            if len(statuses) <= 1:
                stable_count += 1

        return stable_count / len(scenario_ids)

    def unstable_scenarios(self, threshold: float = 1.0) -> list[str]:
        """Return scenario IDs that are not fully stable.

        A scenario is unstable if its status varies across runs.
        *threshold* is currently unused (reserved for future granularity).
        """
        if not self.runs:
            return []

        scenario_ids = [r.scenario_id for r in self.runs[0].scenarios]
        unstable: list[str] = []

        for sid in scenario_ids:
            statuses: set[str] = set()
            for run in self.runs:
                for result in run.scenarios:
                    if result.scenario_id == sid:
                        statuses.add(result.status)
                        break
            if len(statuses) > 1:
                unstable.append(sid)

        return unstable


def run_multirun(
    pipeline: RedTeamPipeline,
    scenarios: list[RedTeamScenario],
    runs: int = 5,
    *,
    attempts: int | None = None,
) -> MultiRunResult:
    """Run *scenarios* through *pipeline* a total of *runs* times.

    Returns a :class:`MultiRunResult` aggregating all runs.
    """
    result = MultiRunResult()
    for _ in range(runs):
        report = pipeline.run_scenarios(scenarios, attempts=attempts)
        result.runs.append(report)
    return result
