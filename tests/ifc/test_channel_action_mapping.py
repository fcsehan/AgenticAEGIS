"""Tests for AEGIS-1802 Channel-to-Action Mapping."""

from __future__ import annotations

import pytest

from aegis.ifc.channel_action_mapping import (
    CHANNEL_ACTION_MAPPING,
    ResponseMode,
    UnmappedChannelError,
    ensure_mapping,
    mapping_by_channel_id,
    search_corpus_and_read_document_are_separate,
    transformation_and_disclosure_are_separate,
    unmapped_channels,
)
from aegis.ifc.channel_registry import CHANNEL_REGISTRY


class TestSchema:
    def test_every_channel_has_a_mapping(self) -> None:
        """AEGIS-1802 acceptance #1: every registered channel must
        have exactly one Channel-to-Action mapping."""
        assert unmapped_channels() == []

    def test_mapping_count_matches_channel_count(self) -> None:
        assert len(CHANNEL_ACTION_MAPPING) == len(CHANNEL_REGISTRY)

    def test_mapping_channel_ids_are_unique(self) -> None:
        ids = [m.channel_id for m in CHANNEL_ACTION_MAPPING]
        assert len(ids) == len(set(ids))

    def test_every_mapping_points_to_a_real_channel(self) -> None:
        registered_ids = {ch.channel_id for ch in CHANNEL_REGISTRY}
        for m in CHANNEL_ACTION_MAPPING:
            assert m.channel_id in registered_ids, m.channel_id


class TestEnsureMapping:
    def test_known_channel_returns_mapping(self) -> None:
        m = ensure_mapping("orchestrator_tool_call")
        assert m.action_type == "invokeTool"

    def test_unknown_channel_raises(self) -> None:
        with pytest.raises(UnmappedChannelError) as exc_info:
            ensure_mapping("ghost_channel")
        assert "ghost_channel" in str(exc_info.value)
        assert "channel_action_mapping.py" in str(exc_info.value)


class TestMappingBy:
    def test_lookup_returns_entry(self) -> None:
        m = mapping_by_channel_id("orchestrator_final_response")
        assert m is not None
        assert m.action_type == "discloseFinalResponse"

    def test_lookup_returns_none_for_unknown(self) -> None:
        assert mapping_by_channel_id("ghost") is None


class TestSeparation:
    def test_search_corpus_and_read_document_are_separate(self) -> None:
        """AEGIS-1802 #4: the two retrieval verbs must NOT be merged."""
        assert search_corpus_and_read_document_are_separate() is True

    def test_search_aggregation_uses_search_corpus(self) -> None:
        m = mapping_by_channel_id("search_aggregation")
        assert m is not None
        assert m.action_type == "searchCorpus"

    def test_orchestrator_tool_result_uses_read_document(self) -> None:
        m = mapping_by_channel_id("orchestrator_tool_result")
        assert m is not None
        assert m.action_type == "readDocument"

    def test_transformation_and_disclosure_are_separate(self) -> None:
        """AEGIS-1802 #5: transformation results must not bleed into
        disclosure paths without an explicit disclosure check."""
        assert transformation_and_disclosure_are_separate() is True


class TestResponseModes:
    def test_disclosure_channels_can_return_full_content(self) -> None:
        m = mapping_by_channel_id("orchestrator_final_response")
        assert m is not None
        assert m.response_mode == ResponseMode.FULL_CONTENT

    def test_retrieval_channels_use_redacted_snippet(self) -> None:
        for ch_id in ("orchestrator_tool_result", "sidecar_broker_read"):
            m = mapping_by_channel_id(ch_id)
            assert m is not None
            assert m.response_mode == ResponseMode.REDACTED_SNIPPET

    def test_audit_only_channel_uses_deny(self) -> None:
        m = mapping_by_channel_id("host_posttooluse_audit")
        assert m is not None
        assert m.response_mode == ResponseMode.DENY

    def test_search_uses_metadata_only(self) -> None:
        """Search must default to metadata-only payloads to limit
        n-document aggregation risk."""
        m = mapping_by_channel_id("search_aggregation")
        assert m is not None
        assert m.response_mode == ResponseMode.METADATA_ONLY


class TestRequiredProposition:
    def test_disclosure_requires_recipient(self) -> None:
        m = mapping_by_channel_id("orchestrator_final_response")
        assert m is not None
        assert "recipient" in m.required_proposition

    def test_external_message_requires_recipient_and_message(self) -> None:
        m = mapping_by_channel_id("external_tool_side_effect")
        assert m is not None
        assert "recipient" in m.required_proposition
        assert "message" in m.required_proposition

    def test_retrieval_requires_path(self) -> None:
        m = mapping_by_channel_id("orchestrator_tool_result")
        assert m is not None
        assert "path" in m.required_proposition

    def test_search_requires_query(self) -> None:
        m = mapping_by_channel_id("search_aggregation")
        assert m is not None
        assert "query" in m.required_proposition


class TestImmutability:
    def test_mapping_is_frozen(self) -> None:
        m = CHANNEL_ACTION_MAPPING[0]
        try:
            m.action_type = "changed"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("ChannelActionMapping must be frozen")


class TestEnumValues:
    def test_response_mode_values(self) -> None:
        assert ResponseMode.DENY.value == "deny"
        assert ResponseMode.METADATA_ONLY.value == "metadata_only"
        assert ResponseMode.REDACTED_SNIPPET.value == "redacted_snippet"
        assert ResponseMode.FULL_CONTENT.value == "full_content"


class TestEndToEndIntegration:
    """The mapping table is meant to be queried alongside the channel
    registry. These tests verify the joint API works without
    surprises."""

    def test_every_registered_channel_has_required_proposition_or_empty(self) -> None:
        """Required-proposition tuple may be empty (control-plane
        channels) but must always be a tuple (not None) so callers
        don't have to special-case."""
        for m in CHANNEL_ACTION_MAPPING:
            assert isinstance(m.required_proposition, tuple), m.channel_id

    def test_every_mapping_has_response_mode(self) -> None:
        for m in CHANNEL_ACTION_MAPPING:
            assert isinstance(m.response_mode, ResponseMode), m.channel_id
