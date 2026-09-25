"""Tests for AEGIS-1901..1904 formal disclosure-action builder."""

from __future__ import annotations

import pytest

from aegis.hardening.taint import TaintLevel, TaintTracker
from aegis.ifc.channel_registry import UnregisteredChannelError
from aegis.ifc.disclosure_action import (
    DisclosureContext,
    DisclosureMetadata,
    TransformationType,
    build_disclosure_action,
    disclosure_metadata_from,
    transformation_type_from_string,
)


class TestTransformationTypeEnum:
    def test_canonical_values(self) -> None:
        for member in TransformationType:
            assert isinstance(member.value, str)

    def test_string_to_enum_known(self) -> None:
        assert transformation_type_from_string("summarize") == TransformationType.SUMMARIZE
        assert transformation_type_from_string("COMPARE") == TransformationType.COMPARE
        assert transformation_type_from_string("  rank ") == TransformationType.RANK

    def test_string_to_enum_unknown_fallback(self) -> None:
        assert transformation_type_from_string("undefined") == TransformationType.NONE
        assert transformation_type_from_string("") == TransformationType.NONE


class TestBuildDisclosureAction:
    def test_basic_action_for_final_response(self) -> None:
        context = DisclosureContext(
            channel_id="orchestrator_final_response",
            recipient="end_user",
            purpose="final_user_response",
            agent_id="agent-1",
        )
        action, mapping, channel = build_disclosure_action(context)
        assert action.action_type == "discloseFinalResponse"
        assert action.agent_id == "agent-1"
        assert action.proposition["recipient"] == "end_user"
        assert action.proposition["purpose"] == "final_user_response"
        assert action.proposition["channel_id"] == "orchestrator_final_response"
        assert action.proposition["transformation_type"] == "none"
        assert mapping.action_type == "discloseFinalResponse"
        assert channel.channel_id == "orchestrator_final_response"

    def test_classification_pulled_from_tracker(self) -> None:
        tracker = TaintTracker()
        tracker.mark(["CANARY-1"], source="test", level=TaintLevel.SECRET)
        context = DisclosureContext(channel_id="orchestrator_final_response")
        action, _, _ = build_disclosure_action(context, tracker=tracker)
        assert action.proposition["sourceClassification"] == "secret"

    def test_classification_defaults_to_public(self) -> None:
        context = DisclosureContext(channel_id="orchestrator_final_response")
        action, _, _ = build_disclosure_action(context, tracker=None)
        assert action.proposition["sourceClassification"] == "public"

    def test_transformation_type_threaded_through(self) -> None:
        context = DisclosureContext(
            channel_id="orchestrator_final_response",
            transformation_type=TransformationType.SUMMARIZE,
        )
        action, _, _ = build_disclosure_action(context)
        assert action.proposition["transformation_type"] == "summarize"

    def test_provenance_sources_threaded_through(self) -> None:
        context = DisclosureContext(
            channel_id="orchestrator_final_response",
            provenance_sources=("intel/briefing.txt", "logs/search.log"),
        )
        action, _, _ = build_disclosure_action(context)
        assert action.proposition["provenance_sources"] == [
            "intel/briefing.txt",
            "logs/search.log",
        ]

    def test_provenance_omitted_when_empty(self) -> None:
        context = DisclosureContext(channel_id="orchestrator_final_response")
        action, _, _ = build_disclosure_action(context)
        assert "provenance_sources" not in action.proposition

    def test_unknown_channel_fails_closed(self) -> None:
        with pytest.raises(UnregisteredChannelError):
            build_disclosure_action(
                DisclosureContext(channel_id="ghost_channel"),
            )

    def test_recipient_default_is_conservative(self) -> None:
        """Per RR-002: never trust an LLM-supplied recipient. The
        default must be a conservative placeholder that fails
        closed under any sensible deontic policy."""
        context = DisclosureContext(channel_id="orchestrator_final_response")
        action, _, _ = build_disclosure_action(context)
        assert action.proposition["recipient"] == "unspecified_recipient"
        assert action.proposition["purpose"] == "unspecified_purpose"

    def test_tool_argument_uses_external_message_action(self) -> None:
        """AEGIS-1902: the same builder produces a disclosure action
        for tool arguments — only the channel and recipient differ."""
        context = DisclosureContext(
            channel_id="external_tool_side_effect",
            recipient="external_api",
            purpose="weekly_status_email",
        )
        action, mapping, _ = build_disclosure_action(context)
        assert action.action_type == "sendExternalMessage"
        assert mapping.required_proposition  # has at least recipient


class TestDisclosureMetadata:
    def test_metadata_pulled_from_context(self) -> None:
        context = DisclosureContext(
            channel_id="orchestrator_final_response",
            recipient="user",
            purpose="final_user_response",
            transformation_type=TransformationType.SUMMARIZE,
            provenance_sources=("a", "b"),
        )
        meta = disclosure_metadata_from(
            context, tracker=None, decision="PERMITTED",
        )
        assert meta.disclosure_checked is True
        assert meta.disclosure_action_type == "discloseFinalResponse"
        assert meta.disclosure_decision == "PERMITTED"
        assert meta.channel_id == "orchestrator_final_response"
        assert meta.transformation_type == "summarize"
        assert meta.source_classification == "public"
        assert meta.recipient == "user"
        assert meta.purpose == "final_user_response"
        assert meta.provenance_sources == ("a", "b")

    def test_metadata_carries_block_reason(self) -> None:
        meta = disclosure_metadata_from(
            DisclosureContext(channel_id="orchestrator_final_response"),
            tracker=None,
            decision="FORBIDDEN",
            block_reason="recipient not whitelisted for SECRET",
        )
        assert meta.disclosure_decision == "FORBIDDEN"
        assert meta.block_reason == "recipient not whitelisted for SECRET"

    def test_metadata_to_dict_round_trip(self) -> None:
        meta = disclosure_metadata_from(
            DisclosureContext(channel_id="orchestrator_final_response"),
            tracker=None,
            decision="PERMITTED",
        )
        payload = meta.to_dict()
        assert payload["disclosure_checked"] is True
        assert payload["disclosure_action_type"] == "discloseFinalResponse"
        assert payload["transformation_type"] == "none"


class TestImmutability:
    def test_context_is_frozen(self) -> None:
        context = DisclosureContext(channel_id="orchestrator_final_response")
        try:
            context.recipient = "x"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("DisclosureContext must be frozen")

    def test_metadata_is_frozen(self) -> None:
        meta = DisclosureMetadata(
            disclosure_checked=True,
            disclosure_action_type="x",
            disclosure_decision="PERMITTED",
            channel_id="y",
            transformation_type="none",
            source_classification="public",
            recipient="r",
            purpose="p",
        )
        try:
            meta.recipient = "changed"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("DisclosureMetadata must be frozen")


class TestProvenancePropagation:
    """AEGIS-1903 acceptance: provenance and transformation context
    survive across processing steps."""

    def test_provenance_passes_through_unchanged(self) -> None:
        sources = ("a.txt", "b.txt", "c.txt")
        context = DisclosureContext(
            channel_id="orchestrator_final_response",
            provenance_sources=sources,
            transformation_type=TransformationType.COMPARE,
        )
        action, _, _ = build_disclosure_action(context)
        assert action.proposition["provenance_sources"] == list(sources)
        assert action.proposition["transformation_type"] == "compare"

    def test_aggregation_signal_distinct_from_summarize(self) -> None:
        """compare ≠ summarize at the proposition level so deontic
        rules can distinguish single-source paraphrasing from multi-
        source aggregation."""
        compare_ctx = DisclosureContext(
            channel_id="orchestrator_final_response",
            transformation_type=TransformationType.COMPARE,
        )
        summarize_ctx = DisclosureContext(
            channel_id="orchestrator_final_response",
            transformation_type=TransformationType.SUMMARIZE,
        )
        compare_action, _, _ = build_disclosure_action(compare_ctx)
        summarize_action, _, _ = build_disclosure_action(summarize_ctx)
        assert (
            compare_action.proposition["transformation_type"]
            != summarize_action.proposition["transformation_type"]
        )
