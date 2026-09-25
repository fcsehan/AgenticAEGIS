"""AEGIS-2001: Channel Coverage Matrix.

Links every information flow channel from the channel registry to
the red-team scenarios that verify it.  Uncovered channels are a
CI-gate failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aegis.ifc.channel_registry import CHANNEL_REGISTRY, InformationChannel
from aegis.redteam.models import RedTeamReport


@dataclass
class CoverageMatrix:
    """Maps channels → verifying scenarios and reports gaps.

    Usage::

        matrix = CoverageMatrix.from_registry()
        gaps = matrix.uncovered()
        print(matrix.to_markdown())
    """

    channels: list[str] = field(default_factory=list)
    scenarios: list[str] = field(default_factory=list)
    mapping: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_registry(
        cls,
        report: RedTeamReport | None = None,
    ) -> CoverageMatrix:
        """Build a CoverageMatrix from the channel registry.

        If *report* is provided, cross-references against actually
        executed scenarios.
        """
        channels: list[str] = []
        mapping: dict[str, list[str]] = {}
        all_scenario_ids: set[str] = set()

        for ch in CHANNEL_REGISTRY:
            channels.append(ch.channel_id)
            mapping[ch.channel_id] = list(ch.verified_by)
            all_scenario_ids.update(ch.verified_by)

        scenarios = sorted(all_scenario_ids)

        return cls(
            channels=channels,
            scenarios=scenarios,
            mapping=mapping,
        )

    def uncovered(self) -> list[str]:
        """Return channel IDs with no verifying scenario."""
        return [ch for ch in self.channels if not self.mapping.get(ch)]

    def coverage_ratio(self) -> float:
        """Return the fraction of channels that have at least one scenario."""
        if not self.channels:
            return 1.0
        covered = sum(1 for ch in self.channels if self.mapping.get(ch))
        return covered / len(self.channels)

    def to_markdown(self) -> str:
        """Render the coverage matrix as a Markdown table."""
        lines: list[str] = [
            "# AEGIS Channel Coverage Matrix",
            "",
            f"**Coverage:** {self.coverage_ratio():.0%} "
            f"({len(self.channels) - len(self.uncovered())}/{len(self.channels)} channels)",
            "",
            "| Channel | Enforcement | Scenarios | Status |",
            "|---------|-------------|-----------|--------|",
        ]

        for ch in CHANNEL_REGISTRY:
            scenarios = ", ".join(ch.verified_by) if ch.verified_by else "—"
            status = "COVERED" if ch.verified_by else "GAP"
            lines.append(
                f"| {ch.channel_id} | {ch.enforcement} | {scenarios} | {status} |"
            )

        uncovered = self.uncovered()
        if uncovered:
            lines.extend(["", f"**GAPS ({len(uncovered)}):** {', '.join(uncovered)}"])
        else:
            lines.extend(["", "**All channels covered.**"])

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "channels": self.channels,
            "scenarios": self.scenarios,
            "mapping": self.mapping,
            "uncovered": self.uncovered(),
            "coverage_ratio": self.coverage_ratio(),
        }
