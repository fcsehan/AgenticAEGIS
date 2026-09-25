"""AEGIS-1606: Security Scorecard.

Aggregates red-team reports, contract violations, and multi-run
stability results into a release-eligibility scorecard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aegis.redteam.contracts import ContractViolation
from aegis.redteam.models import RedTeamReport
from aegis.redteam.multirun import MultiRunResult


@dataclass(frozen=True, slots=True)
class ScorecardSection:
    """A single section of the security scorecard."""

    name: str
    passed: bool
    score: float  # 0.0 to 1.0
    details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SecurityScorecard:
    """Aggregate security scorecard for release eligibility.

    A deployment is release-eligible if all sections pass.
    """

    sections: tuple[ScorecardSection, ...]

    def release_eligible(self) -> bool:
        """True if all sections pass."""
        return all(s.passed for s in self.sections)

    def to_markdown(self) -> str:
        """Render the scorecard as a Markdown report."""
        lines: list[str] = ["# AEGIS Security Scorecard", ""]

        status = "PASS" if self.release_eligible() else "FAIL"
        lines.append(f"**Release Eligible:** {status}")
        lines.append("")

        for section in self.sections:
            icon = "+" if section.passed else "-"
            lines.append(f"## [{icon}] {section.name} ({section.score:.0%})")
            for detail in section.details:
                lines.append(f"- {detail}")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "release_eligible": self.release_eligible(),
            "sections": [
                {
                    "name": s.name,
                    "passed": s.passed,
                    "score": s.score,
                    "details": list(s.details),
                }
                for s in self.sections
            ],
        }


class ScorecardBuilder:
    """Incrementally builds a :class:`SecurityScorecard`.

    Usage::

        builder = ScorecardBuilder()
        builder.add_redteam_report(report)
        builder.add_contract_violations(violations)
        builder.add_multirun_stability(multirun_result)
        scorecard = builder.build()
    """

    def __init__(self) -> None:
        self._sections: list[ScorecardSection] = []

    def add_redteam_report(self, report: RedTeamReport) -> None:
        """Score the red-team results."""
        total = len(report.scenarios)
        if total == 0:
            self._sections.append(ScorecardSection(
                name="Red-Team Scenarios",
                passed=True,
                score=1.0,
                details=("No scenarios executed.",),
            ))
            return

        passed = sum(1 for r in report.scenarios if r.passed)
        score = passed / total
        details: list[str] = []
        for result in report.scenarios:
            status_icon = "PASS" if result.passed else "FAIL"
            details.append(f"[{status_icon}] {result.scenario_id}: {result.status}")

        self._sections.append(ScorecardSection(
            name="Red-Team Scenarios",
            passed=report.passed,
            score=score,
            details=tuple(details),
        ))

    def add_contract_violations(self, violations: list[ContractViolation]) -> None:
        """Score host-contract compliance."""
        critical = [v for v in violations if v.severity == "critical"]
        high = [v for v in violations if v.severity == "high"]

        passed = len(critical) == 0 and len(high) == 0
        total_weight = max(len(violations), 1)
        score = 1.0 - (len(violations) / total_weight) if violations else 1.0

        details: list[str] = []
        for v in violations:
            details.append(f"[{v.severity.upper()}] {v.code}: {v.message}")

        if not violations:
            details.append("All host contracts satisfied.")

        self._sections.append(ScorecardSection(
            name="Host Contracts",
            passed=passed,
            score=score,
            details=tuple(details),
        ))

    def add_multirun_stability(self, results: MultiRunResult) -> None:
        """Score multi-run stability."""
        score = results.stability_score()
        unstable = results.unstable_scenarios()

        details: list[str] = [
            f"Runs: {len(results.runs)}",
            f"Stability: {score:.0%}",
        ]
        for sid in unstable:
            details.append(f"Unstable: {sid}")

        self._sections.append(ScorecardSection(
            name="Multi-Run Stability",
            passed=score >= 0.8,
            score=score,
            details=tuple(details),
        ))

    def add_guard_integrity(
        self,
        *,
        bypass_count: int,
        channels_verified: int,
        channels_total: int,
        formal_properties_proven: int = 0,
        ddic_soundness_coverage: float = 0.0,
    ) -> None:
        """Score Guard integrity metrics (AEGIS-2004).

        Release-eligible requires:
        - bypass_count == 0
        - channels_verified == channels_total
        """
        passed = bypass_count == 0 and channels_verified >= channels_total
        if channels_total > 0:
            channel_ratio = channels_verified / channels_total
        else:
            channel_ratio = 1.0

        score = 1.0 if passed else max(0.0, channel_ratio * (1.0 if bypass_count == 0 else 0.5))

        details: list[str] = [
            f"Bypass findings: {bypass_count}",
            f"Channels verified: {channels_verified}/{channels_total}",
            f"Formal properties proven: {formal_properties_proven}",
            f"DDIC soundness coverage: {ddic_soundness_coverage:.0%}",
        ]

        self._sections.append(ScorecardSection(
            name="Guard Integrity",
            passed=passed,
            score=score,
            details=tuple(details),
        ))

    def build(self) -> SecurityScorecard:
        """Build the final scorecard."""
        return SecurityScorecard(sections=tuple(self._sections))
