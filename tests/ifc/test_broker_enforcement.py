"""Tests for AEGIS-1803 mandatory-broker-enforcement helpers."""

from __future__ import annotations

import time

import pytest

from aegis.ifc.broker_enforcement import (
    UNGUARDED_RETRIEVAL_CODE,
    BrokerCall,
    BrokerCallLedger,
    UnguardedRetrievalError,
    assert_broker_mediated,
)


class TestBrokerCallLedger:
    def test_record_returns_entry(self) -> None:
        ledger = BrokerCallLedger()
        call = ledger.record(
            channel_id="orchestrator_tool_result",
            action_type="readDocument",
            action_id="audit-1",
        )
        assert isinstance(call, BrokerCall)
        assert call.channel_id == "orchestrator_tool_result"
        assert call.action_type == "readDocument"

    def test_has_recent_call_within_window(self) -> None:
        ledger = BrokerCallLedger()
        ledger.record("orchestrator_tool_result", "readDocument", "x")
        assert ledger.has_recent_call(
            "orchestrator_tool_result", within_seconds=5.0,
        ) is True

    def test_has_recent_call_outside_window(self) -> None:
        ledger = BrokerCallLedger()
        # Manually inject a stale call so we don't have to sleep in tests.
        ledger.calls.append(
            BrokerCall(
                channel_id="orchestrator_tool_result",
                action_type="readDocument",
                action_id="x",
                timestamp=time.monotonic() - 60.0,  # 60 s ago
            ),
        )
        assert ledger.has_recent_call(
            "orchestrator_tool_result", within_seconds=5.0,
        ) is False

    def test_has_call_for_action_strict_match(self) -> None:
        ledger = BrokerCallLedger()
        ledger.record("orchestrator_tool_result", "readDocument", "audit-42")
        assert ledger.has_call_for_action(
            "orchestrator_tool_result", "audit-42",
        ) is True
        assert ledger.has_call_for_action(
            "orchestrator_tool_result", "audit-99",
        ) is False

    def test_record_raises_for_unregistered_channel(self) -> None:
        from aegis.ifc.channel_registry import UnregisteredChannelError

        ledger = BrokerCallLedger()
        with pytest.raises(UnregisteredChannelError):
            ledger.record("ghost_channel", "x", "y")


class TestAssertBrokerMediated:
    def test_non_broker_channel_is_noop(self) -> None:
        ledger = BrokerCallLedger()
        # orchestrator_tool_call has requires_broker=False — nothing
        # to assert.
        assert_broker_mediated(ledger, "orchestrator_tool_call")

    def test_broker_channel_with_recent_call_passes(self) -> None:
        ledger = BrokerCallLedger()
        ledger.record(
            "orchestrator_tool_result", "readDocument", "audit-1",
        )
        assert_broker_mediated(ledger, "orchestrator_tool_result")

    def test_broker_channel_without_call_raises(self) -> None:
        ledger = BrokerCallLedger()
        with pytest.raises(UnguardedRetrievalError) as exc_info:
            assert_broker_mediated(ledger, "orchestrator_tool_result")
        assert exc_info.value.code == UNGUARDED_RETRIEVAL_CODE
        assert exc_info.value.channel_id == "orchestrator_tool_result"

    def test_broker_channel_with_stale_call_raises(self) -> None:
        ledger = BrokerCallLedger()
        ledger.calls.append(
            BrokerCall(
                channel_id="orchestrator_tool_result",
                action_type="readDocument",
                action_id="x",
                timestamp=time.monotonic() - 60.0,
            ),
        )
        with pytest.raises(UnguardedRetrievalError):
            assert_broker_mediated(
                ledger, "orchestrator_tool_result",
                within_seconds=5.0,
            )

    def test_strict_action_id_match_required_when_supplied(self) -> None:
        ledger = BrokerCallLedger()
        ledger.record(
            "orchestrator_tool_result", "readDocument", "audit-42",
        )
        # Same channel, different action ID → still raises.
        with pytest.raises(UnguardedRetrievalError):
            assert_broker_mediated(
                ledger, "orchestrator_tool_result",
                action_id="audit-99",
            )
        # Same channel, matching action ID → passes.
        assert_broker_mediated(
            ledger, "orchestrator_tool_result",
            action_id="audit-42",
        )


class TestSearchVsReadSeparation:
    """AEGIS-1803 acceptance: searchCorpus and readDocument are checked
    SEPARATELY at runtime. A read does not satisfy a search."""

    def test_read_call_does_not_satisfy_search_requirement(self) -> None:
        ledger = BrokerCallLedger()
        ledger.record(
            "orchestrator_tool_result", "readDocument", "x",
        )
        # search_aggregation is a different channel.
        with pytest.raises(UnguardedRetrievalError):
            assert_broker_mediated(ledger, "search_aggregation")

    def test_search_call_does_not_satisfy_read_requirement(self) -> None:
        ledger = BrokerCallLedger()
        ledger.record(
            "search_aggregation", "searchCorpus", "x",
        )
        with pytest.raises(UnguardedRetrievalError):
            assert_broker_mediated(ledger, "orchestrator_tool_result")


class TestArchitecturalIntegration:
    def test_unguarded_retrieval_code_is_in_bypass_codes(self) -> None:
        """The finding code must be in BYPASS_FINDING_CODES so the
        scorecard automatically counts UnguardedRetrievalError as a
        bypass."""
        from aegis.redteam.bypass_proof import BYPASS_FINDING_CODES

        assert UNGUARDED_RETRIEVAL_CODE in BYPASS_FINDING_CODES

    def test_error_message_names_the_channel(self) -> None:
        ledger = BrokerCallLedger()
        try:
            assert_broker_mediated(ledger, "orchestrator_tool_result")
        except UnguardedRetrievalError as e:
            assert "orchestrator_tool_result" in str(e)
            assert e.channel_id == "orchestrator_tool_result"
