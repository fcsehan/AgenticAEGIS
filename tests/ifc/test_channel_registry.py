"""Tests for the AEGIS-1801 + AEGIS-1808 ChannelRegistry."""

from __future__ import annotations

import pytest

from aegis.ifc.channel_registry import (
    CHANNEL_REGISTRY,
    ChannelDirection,
    ChannelKind,
    MediationType,
    UnregisteredChannelError,
    all_verified_scenario_ids,
    channel_by_id,
    channels_by_kind,
    channels_requiring_broker,
    channels_requiring_guard,
    ensure_registered,
    uncovered_channels,
)


class TestSchema:
    def test_all_channels_have_kind(self) -> None:
        for ch in CHANNEL_REGISTRY:
            assert isinstance(ch.kind, ChannelKind), ch.channel_id

    def test_all_channels_have_direction(self) -> None:
        for ch in CHANNEL_REGISTRY:
            assert isinstance(ch.direction, ChannelDirection), ch.channel_id

    def test_all_channels_have_host_surface(self) -> None:
        for ch in CHANNEL_REGISTRY:
            assert ch.host_surface != "", (
                f"channel {ch.channel_id} missing host_surface"
            )

    def test_all_channels_have_mediation_type(self) -> None:
        for ch in CHANNEL_REGISTRY:
            assert isinstance(ch.mediation_type, MediationType), ch.channel_id

    def test_unique_channel_ids(self) -> None:
        ids = [ch.channel_id for ch in CHANNEL_REGISTRY]
        assert len(ids) == len(set(ids)), "duplicate channel IDs in registry"


class TestKindFiltering:
    def test_disclosure_channels(self) -> None:
        disclosures = channels_by_kind(ChannelKind.DISCLOSURE)
        assert any(ch.channel_id == "orchestrator_final_response" for ch in disclosures)
        assert any(ch.channel_id == "external_tool_side_effect" for ch in disclosures)

    def test_retrieval_channels(self) -> None:
        retrievals = channels_by_kind(ChannelKind.RETRIEVAL)
        assert any(ch.channel_id == "orchestrator_tool_result" for ch in retrievals)
        assert any(ch.channel_id == "sidecar_broker_read" for ch in retrievals)

    def test_discovery_channels(self) -> None:
        discoveries = channels_by_kind(ChannelKind.DISCOVERY)
        assert any(ch.channel_id == "classification_manifest" for ch in discoveries)
        assert any(ch.channel_id == "search_aggregation" for ch in discoveries)


class TestEnsureRegistered:
    def test_known_channel_returns_entry(self) -> None:
        ch = ensure_registered("orchestrator_tool_call")
        assert ch.channel_id == "orchestrator_tool_call"

    def test_unknown_channel_raises_with_helpful_message(self) -> None:
        with pytest.raises(UnregisteredChannelError) as exc_info:
            ensure_registered("ghost_channel")
        msg = str(exc_info.value)
        assert "ghost_channel" in msg
        assert "channel_registry.py" in msg
        # The message should list available channels for ergonomics.
        assert "orchestrator_tool_call" in msg

    def test_empty_string_raises(self) -> None:
        with pytest.raises(UnregisteredChannelError):
            ensure_registered("")


class TestRequirements:
    def test_channels_requiring_broker(self) -> None:
        broker_channels = channels_requiring_broker()
        broker_ids = {ch.channel_id for ch in broker_channels}
        # The four explicitly broker-mediated channels.
        assert "orchestrator_tool_result" in broker_ids
        assert "sidecar_broker_read" in broker_ids
        assert "search_aggregation" in broker_ids

    def test_channels_requiring_broker_have_broker_mediation(self) -> None:
        for ch in channels_requiring_broker():
            assert ch.mediation_type == MediationType.BROKER, ch.channel_id

    def test_channels_requiring_guard(self) -> None:
        guarded = channels_requiring_guard()
        # All but the audit-only postToolUse channel.
        guarded_ids = {ch.channel_id for ch in guarded}
        assert "orchestrator_tool_call" in guarded_ids
        assert "host_posttooluse_audit" not in guarded_ids


class TestExistingApi:
    """Pre-existing AEGIS-1808 functions still work."""

    def test_channel_by_id(self) -> None:
        ch = channel_by_id("orchestrator_tool_call")
        assert ch is not None
        assert ch.enforcement == "action_check"

    def test_channel_by_id_unknown(self) -> None:
        assert channel_by_id("ghost") is None

    def test_uncovered_channels_returns_list(self) -> None:
        # All current channels have at least one verifying scenario.
        assert uncovered_channels() == []

    def test_all_verified_scenario_ids(self) -> None:
        ids = all_verified_scenario_ids()
        assert "01_public_summary_no_canary_leak" in ids
        assert "22_broker_mandatory_no_fallback" in ids


class TestImmutability:
    def test_channel_is_frozen(self) -> None:
        ch = CHANNEL_REGISTRY[0]
        try:
            ch.channel_id = "changed"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("InformationChannel must be frozen")


class TestArchitecturalConsistency:
    """Locks in consistency rules across the registry."""

    def test_broker_mediated_implies_requires_broker(self) -> None:
        for ch in CHANNEL_REGISTRY:
            if ch.mediation_type == MediationType.BROKER:
                assert ch.requires_broker is True, ch.channel_id

    def test_disclosure_channels_are_outbound(self) -> None:
        """A disclosure (data leaves the perimeter) must be outbound by
        definition. Catches misclassification."""
        for ch in channels_by_kind(ChannelKind.DISCLOSURE):
            assert ch.direction == ChannelDirection.OUTBOUND, ch.channel_id
