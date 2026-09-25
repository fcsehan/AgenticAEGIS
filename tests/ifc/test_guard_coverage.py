"""Tests for AEGIS-2001 + 2002 Guard-Coverage four-dimensional analysis."""

from __future__ import annotations

import json

from aegis.guard.registry import ActionTypeRegistry
from aegis.ifc.guard_coverage import (
    CoverageDimension,
    analyze_guard_coverage,
    report_uncovered,
)
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader


def _registry_with_actions(*action_types: str) -> ActionTypeRegistry:
    kb = KnowledgeBase()
    if action_types:
        loader = MeldLoader(kb)
        body = "\n".join(f"(isa {t} ActionType)" for t in action_types)
        loader.load_string(
            f"(case TestVocabMt)\n{body}\n",
            file="test.meld",
        )
    kb.freeze()
    return ActionTypeRegistry.from_kb(kb)


class TestCoverageDimension:
    def test_ratio_zero_total(self) -> None:
        d = CoverageDimension(name="x", covered=0, total=0)
        assert d.ratio == 1.0
        assert d.percent == 100

    def test_ratio_partial(self) -> None:
        d = CoverageDimension(name="x", covered=3, total=4)
        assert d.ratio == 0.75
        assert d.percent == 75

    def test_to_dict(self) -> None:
        d = CoverageDimension(
            name="x", covered=3, total=4,
            uncovered_channel_ids=("a", "b"),
        )
        payload = d.to_dict()
        assert payload["name"] == "x"
        assert payload["covered"] == 3
        assert payload["uncovered_channel_ids"] == ["a", "b"]


class TestChannelCoverage:
    def test_full_coverage_under_default_registry(self) -> None:
        """AEGIS-1802 ensures every registered channel has a mapping;
        Channel Coverage must therefore be 100%."""
        report = analyze_guard_coverage(_registry_with_actions())
        assert report.channel_coverage.ratio == 1.0
        assert report.channel_coverage.uncovered_channel_ids == ()


class TestPolicyCoverage:
    def test_zero_coverage_with_empty_registry(self) -> None:
        """No actions in the registry → all channels uncovered for
        policy. The empty case must surface the gap, not hide it."""
        report = analyze_guard_coverage(_registry_with_actions())
        assert report.policy_coverage.covered == 0
        # All 10 channels are listed as uncovered.
        assert len(report.policy_coverage.uncovered_channel_ids) == 10

    def test_partial_coverage_with_some_actions(self) -> None:
        """A registry that knows readDocument but not searchCorpus
        covers some channels but not others."""
        registry = _registry_with_actions("readDocument")
        report = analyze_guard_coverage(registry)
        # readDocument backs 2 channels (orchestrator_tool_result,
        # sidecar_broker_read).
        assert report.policy_coverage.covered >= 2
        # searchCorpus channel is uncovered.
        uncovered = set(report.policy_coverage.uncovered_channel_ids)
        assert "search_aggregation" in uncovered

    def test_full_coverage_with_all_action_types(self) -> None:
        from aegis.ifc.channel_action_mapping import CHANNEL_ACTION_MAPPING
        all_actions = sorted({m.action_type for m in CHANNEL_ACTION_MAPPING})
        registry = _registry_with_actions(*all_actions)
        report = analyze_guard_coverage(registry)
        assert report.policy_coverage.ratio == 1.0


class TestTestCoverage:
    def test_full_coverage_under_default_registry(self) -> None:
        """All current channels have at least one verifying scenario."""
        report = analyze_guard_coverage(_registry_with_actions())
        assert report.test_coverage.ratio == 1.0


class TestDisclosureCoverage:
    def test_full_coverage_under_default_registry(self) -> None:
        report = analyze_guard_coverage(_registry_with_actions())
        # Every disclosure channel today uses OUTPUT_GUARD or ACTION_CHECK
        # which both count as covered until Epic 19 lands.
        assert report.disclosure_coverage.ratio == 1.0


class TestAggregation:
    def test_all_full_coverage_when_dimensions_full(self) -> None:
        from aegis.ifc.channel_action_mapping import CHANNEL_ACTION_MAPPING
        all_actions = sorted({m.action_type for m in CHANNEL_ACTION_MAPPING})
        registry = _registry_with_actions(*all_actions)
        report = analyze_guard_coverage(registry)
        assert report.all_full_coverage is True

    def test_all_full_coverage_false_when_policy_gaps(self) -> None:
        report = analyze_guard_coverage(_registry_with_actions())
        assert report.all_full_coverage is False  # policy gap

    def test_to_json_roundtrip(self) -> None:
        report = analyze_guard_coverage(_registry_with_actions())
        payload = json.loads(report.to_json())
        assert "channel_coverage" in payload
        assert "policy_coverage" in payload
        assert "test_coverage" in payload
        assert "disclosure_coverage" in payload
        assert "all_full_coverage" in payload

    def test_to_markdown_renders_table(self) -> None:
        report = analyze_guard_coverage(_registry_with_actions())
        md = report.to_markdown()
        assert "# AEGIS Guard Coverage Report" in md
        assert "Channel Coverage" in md
        assert "Policy Coverage" in md
        assert "partial_guard_coverage" in md  # because policy gaps exist

    def test_to_markdown_full_coverage_phrase(self) -> None:
        from aegis.ifc.channel_action_mapping import CHANNEL_ACTION_MAPPING
        all_actions = sorted({m.action_type for m in CHANNEL_ACTION_MAPPING})
        registry = _registry_with_actions(*all_actions)
        md = analyze_guard_coverage(registry).to_markdown()
        assert "full_guard_coverage" in md


class TestReportUncovered:
    def test_returns_union_of_uncovered_channels(self) -> None:
        report = analyze_guard_coverage(_registry_with_actions())
        # Only policy gaps exist; report_uncovered returns those channels.
        uncovered = report_uncovered(report)
        assert len(uncovered) == 10  # all channels uncovered for policy

    def test_empty_when_full_coverage(self) -> None:
        from aegis.ifc.channel_action_mapping import CHANNEL_ACTION_MAPPING
        all_actions = sorted({m.action_type for m in CHANNEL_ACTION_MAPPING})
        registry = _registry_with_actions(*all_actions)
        report = analyze_guard_coverage(registry)
        assert report_uncovered(report) == []


class TestNoneRegistry:
    def test_none_registry_yields_zero_policy_coverage(self) -> None:
        """Convenience path for CI jobs that only verify registry/mapping
        artefacts and don't load a domain."""
        report = analyze_guard_coverage(None)
        assert report.policy_coverage.covered == 0


class TestMetadata:
    def test_metadata_includes_registry_sizes(self) -> None:
        report = analyze_guard_coverage(_registry_with_actions())
        assert "registry_size" in report.metadata
        assert "mapping_size" in report.metadata
