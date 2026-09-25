"""Four-dimensional Guard-Coverage analysis (AEGIS-2001 + 2002, Epic 20).

Coverage is the product metric for the 100%-Guard claim. This module
analyses four orthogonal dimensions across the canonical channel
registry (AEGIS-1801) and the channel-to-action mapping (AEGIS-1802):

1. **Channel Coverage** — fraction of registered channels with a
   Channel-to-Action mapping. Without a mapping the channel is
   architecturally unguardable.
2. **Policy Coverage** — fraction of channels backed by an explicit
   ``.meld`` norm rather than relying on CWA fallback.
3. **Test Coverage** — fraction of channels with at least one
   verifying red-team scenario (the existing
   ``InformationChannel.verified_by`` field).
4. **Disclosure Coverage** — fraction of disclosure-kind channels that
   declare a formal disclosure mediation (Epic 19 will tighten this).

The output is JSON-serialisable + Markdown-renderable so dashboards
and CI gates can consume it directly.

Per AEGIS-2001 acceptance: "A release without a coverage report is
not release-eligible." The release-gate integration lives in
``aegis/ifc/host_contract.evaluate_release_gate``; this module
provides the coverage half of that gate.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field

from aegis.guard.registry import ActionTypeRegistry
from aegis.ifc.channel_action_mapping import (
    CHANNEL_ACTION_MAPPING,
    ChannelActionMapping,
    unmapped_channels,
)
from aegis.ifc.channel_registry import (
    CHANNEL_REGISTRY,
    ChannelKind,
    InformationChannel,
    channels_by_kind,
)


@dataclass(frozen=True, slots=True)
class CoverageDimension:
    """One dimension of the four-dimensional coverage metric."""

    name: str
    """Human-readable dimension name."""

    covered: int
    """Number of channels that satisfy the dimension."""

    total: int
    """Number of channels considered for this dimension."""

    uncovered_channel_ids: tuple[str, ...] = ()
    """Channel IDs that fail the dimension. Surfaced for actionable
    reporting; auditors get the gap list directly."""

    @property
    def ratio(self) -> float:
        if self.total == 0:
            return 1.0
        return self.covered / self.total

    @property
    def percent(self) -> int:
        return int(round(self.ratio * 100))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "covered": self.covered,
            "total": self.total,
            "ratio": self.ratio,
            "percent": self.percent,
            "uncovered_channel_ids": list(self.uncovered_channel_ids),
        }


@dataclass(frozen=True, slots=True)
class GuardCoverageReport:
    """Aggregated four-dimensional coverage report.

    Use ``to_json`` for machine consumption (CI gates) and
    ``to_markdown`` for human review.
    """

    channel_coverage: CoverageDimension
    policy_coverage: CoverageDimension
    test_coverage: CoverageDimension
    disclosure_coverage: CoverageDimension

    metadata: dict[str, str] = field(default_factory=dict)

    def all_dimensions(self) -> tuple[CoverageDimension, ...]:
        return (
            self.channel_coverage,
            self.policy_coverage,
            self.test_coverage,
            self.disclosure_coverage,
        )

    @property
    def all_full_coverage(self) -> bool:
        """True iff every dimension is at 100%. The 100%-Guard claim
        gate consumes this directly."""
        return all(d.ratio >= 1.0 for d in self.all_dimensions())

    def to_dict(self) -> dict:
        return {
            "channel_coverage": self.channel_coverage.to_dict(),
            "policy_coverage": self.policy_coverage.to_dict(),
            "test_coverage": self.test_coverage.to_dict(),
            "disclosure_coverage": self.disclosure_coverage.to_dict(),
            "all_full_coverage": self.all_full_coverage,
            "metadata": dict(self.metadata),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        lines = ["# AEGIS Guard Coverage Report", ""]
        lines.append("| Dimension | Covered / Total | % | Status |")
        lines.append("|---|---|---|---|")
        for d in self.all_dimensions():
            status = "✓" if d.ratio >= 1.0 else "GAP"
            lines.append(
                f"| {d.name} | {d.covered} / {d.total} | {d.percent}% | {status} |"
            )
        lines.append("")
        if self.all_full_coverage:
            lines.append(
                "**All dimensions at 100% — "
                "eligible for `full_guard_coverage` claim.**",
            )
        else:
            lines.append(
                "**Gaps detected — release falls back to "
                "`partial_guard_coverage` claim.**",
            )
        # Gap-Detail-Section
        for d in self.all_dimensions():
            if d.uncovered_channel_ids:
                lines.append("")
                lines.append(f"### {d.name} gaps")
                for ch in d.uncovered_channel_ids:
                    lines.append(f"- {ch}")
        return "\n".join(lines)


# ── Per-dimension analyzers (AEGIS-2002) ───────────────────────────


def _analyze_channel_coverage() -> CoverageDimension:
    """Channel = registered AND has Channel-to-Action mapping.

    Per AEGIS-2002: a channel without a mapping is unguardable, so
    counts as uncovered regardless of any other property.
    """
    unmapped = unmapped_channels()
    return CoverageDimension(
        name="Channel Coverage",
        covered=len(CHANNEL_REGISTRY) - len(unmapped),
        total=len(CHANNEL_REGISTRY),
        uncovered_channel_ids=tuple(ch.channel_id for ch in unmapped),
    )


def _channels_with_explicit_norm(
    registry: ActionTypeRegistry,
    mappings: Iterable[ChannelActionMapping],
) -> set[str]:
    """A channel has policy coverage when its action_type is registered
    in the ActionTypeRegistry (i.e. a domain explicitly declared the
    action). This is a conservative proxy for "MELD norm exists" — the
    registry is populated from `.meld` files via VocabularyLoader, so
    a registered action_type implies at least one MELD declaration.
    """
    covered: set[str] = set()
    for m in mappings:
        if registry.is_known(m.action_type):
            covered.add(m.channel_id)
    return covered


def _analyze_policy_coverage(registry: ActionTypeRegistry) -> CoverageDimension:
    covered_ids = _channels_with_explicit_norm(registry, CHANNEL_ACTION_MAPPING)
    uncovered_ids = sorted(
        ch.channel_id for ch in CHANNEL_REGISTRY
        if ch.channel_id not in covered_ids
    )
    return CoverageDimension(
        name="Policy Coverage",
        covered=len(covered_ids),
        total=len(CHANNEL_REGISTRY),
        uncovered_channel_ids=tuple(uncovered_ids),
    )


def _analyze_test_coverage() -> CoverageDimension:
    """Test coverage = channels with at least one verifying red-team
    scenario. Reuses the existing ``InformationChannel.verified_by``
    field that AEGIS-1808 already populated."""
    uncovered_ids = tuple(
        ch.channel_id for ch in CHANNEL_REGISTRY if not ch.verified_by
    )
    return CoverageDimension(
        name="Test Coverage",
        covered=len(CHANNEL_REGISTRY) - len(uncovered_ids),
        total=len(CHANNEL_REGISTRY),
        uncovered_channel_ids=uncovered_ids,
    )


def _analyze_disclosure_coverage() -> CoverageDimension:
    """Disclosure channels need an explicit disclosure mechanism.

    Today the existing channels of kind DISCLOSURE rely either on
    OUTPUT_GUARD (final-response) or ACTION_CHECK (external messages).
    Epic 19 will introduce DISCLOSURE_GATE as the formal mechanism;
    until then we accept either as "covered" but flag a future-work
    note in the metadata.
    """
    disclosure = channels_by_kind(ChannelKind.DISCLOSURE)
    uncovered_ids: list[str] = []
    for ch in disclosure:
        # A disclosure channel is uncovered if its mediation_type is
        # not one of the three accepted-today values.
        if ch.mediation_type.value not in {
            "output_guard",
            "action_check",
            "disclosure_gate",
        }:
            uncovered_ids.append(ch.channel_id)
    return CoverageDimension(
        name="Disclosure Coverage",
        covered=len(disclosure) - len(uncovered_ids),
        total=len(disclosure),
        uncovered_channel_ids=tuple(uncovered_ids),
    )


def analyze_guard_coverage(
    registry: ActionTypeRegistry | None = None,
) -> GuardCoverageReport:
    """Compute the full four-dimensional coverage report.

    ``registry`` may be ``None`` for environments that do not have a
    loaded domain (e.g. CI jobs verifying just the registry/mapping
    artefacts). In that case Policy Coverage falls back to all-uncovered
    so the gap is honest.
    """
    if registry is None:
        # Build an empty registry; nothing is "known", so policy
        # coverage will be 0% — matching the fail-closed intuition.
        from aegis.kb.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        kb.freeze()
        registry = ActionTypeRegistry.from_kb(kb)

    return GuardCoverageReport(
        channel_coverage=_analyze_channel_coverage(),
        policy_coverage=_analyze_policy_coverage(registry),
        test_coverage=_analyze_test_coverage(),
        disclosure_coverage=_analyze_disclosure_coverage(),
        metadata={
            "registry_size": str(len(CHANNEL_REGISTRY)),
            "mapping_size": str(len(CHANNEL_ACTION_MAPPING)),
        },
    )


def report_uncovered(report: GuardCoverageReport) -> list[InformationChannel]:
    """Convenience: return the union of all uncovered channels across
    dimensions, deduplicated. Useful for one-line CI summaries."""
    ids: set[str] = set()
    for d in report.all_dimensions():
        ids.update(d.uncovered_channel_ids)
    return [ch for ch in CHANNEL_REGISTRY if ch.channel_id in ids]
