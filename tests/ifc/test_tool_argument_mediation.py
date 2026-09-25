"""Tests for AEGIS-1804 tool-argument disclosure mediation."""

from __future__ import annotations

import time

from aegis.hardening.taint import TaintLevel, TaintTracker
from aegis.ifc.tool_argument_mediation import (
    MediationDecision,
    MediationVerdict,
    TaintHit,
    mediate_tool_arguments,
)


def _tracker_with(*values: str, level: TaintLevel = TaintLevel.SECRET) -> TaintTracker:
    tracker = TaintTracker()
    tracker.mark(list(values), source="test", level=level)
    return tracker


class TestAllow:
    def test_empty_arguments_allow(self) -> None:
        verdict = mediate_tool_arguments({}, _tracker_with("CANARY-1"))
        assert verdict.decision == MediationDecision.ALLOW

    def test_no_taint_in_arguments_allow(self) -> None:
        verdict = mediate_tool_arguments(
            {"recipient": "alice@example.com", "subject": "Weekly status"},
            _tracker_with("CANARY-1"),
        )
        assert verdict.decision == MediationDecision.ALLOW
        assert verdict.hits == ()

    def test_empty_tracker_allow(self) -> None:
        verdict = mediate_tool_arguments(
            {"body": "anything"},
            TaintTracker(),
        )
        assert verdict.decision == MediationDecision.ALLOW


class TestBlockTopLevel:
    def test_top_level_string_with_taint_blocks(self) -> None:
        verdict = mediate_tool_arguments(
            {"message": "report contains CANARY-7719 fragment"},
            _tracker_with("CANARY-7719"),
        )
        assert verdict.decision == MediationDecision.BLOCK
        assert len(verdict.hits) == 1
        assert verdict.hits[0].argument_path == "message"
        assert verdict.hits[0].marker.value == "CANARY-7719"

    def test_block_carries_channel_id(self) -> None:
        verdict = mediate_tool_arguments(
            {"x": "CANARY-1"},
            _tracker_with("CANARY-1"),
            channel_id="external_tool_side_effect",
        )
        assert verdict.channel_id == "external_tool_side_effect"


class TestBlockNested:
    def test_nested_dict_block(self) -> None:
        verdict = mediate_tool_arguments(
            {"payload": {"body": "CANARY-X is here", "subject": "ok"}},
            _tracker_with("CANARY-X"),
        )
        assert verdict.decision == MediationDecision.BLOCK
        assert verdict.hits[0].argument_path == "payload.body"

    def test_list_value_block(self) -> None:
        verdict = mediate_tool_arguments(
            {"recipients": ["alice", "CANARY-Y leak", "bob"]},
            _tracker_with("CANARY-Y"),
        )
        assert verdict.decision == MediationDecision.BLOCK
        assert verdict.hits[0].argument_path == "recipients[1]"

    def test_deeply_nested_block(self) -> None:
        verdict = mediate_tool_arguments(
            {"a": {"b": [{"c": "leaks CANARY-Z"}]}},
            _tracker_with("CANARY-Z"),
        )
        assert verdict.decision == MediationDecision.BLOCK
        assert verdict.hits[0].argument_path == "a.b[0].c"


class TestMultipleHits:
    def test_multiple_taints_collected(self) -> None:
        verdict = mediate_tool_arguments(
            {"a": "CANARY-1", "b": "CANARY-2 also leaks"},
            _tracker_with("CANARY-1", "CANARY-2"),
        )
        assert verdict.decision == MediationDecision.BLOCK
        paths = {hit.argument_path for hit in verdict.hits}
        assert paths == {"a", "b"}


class TestTypeFiltering:
    def test_non_string_values_skipped(self) -> None:
        """Non-string values can't carry taint markers (markers are
        strings). The walk must not crash on int/bool/None."""
        verdict = mediate_tool_arguments(
            {"num": 42, "flag": True, "empty": None, "ratio": 3.14},
            _tracker_with("CANARY-1"),
        )
        assert verdict.decision == MediationDecision.ALLOW

    def test_mixed_types_with_taint_only_in_string(self) -> None:
        verdict = mediate_tool_arguments(
            {"num": 42, "msg": "CANARY-1 is here"},
            _tracker_with("CANARY-1"),
        )
        assert verdict.decision == MediationDecision.BLOCK
        assert verdict.hits[0].argument_path == "msg"


class TestLatency:
    def test_50x50_workload_under_5ms(self) -> None:
        """AEGIS-1804 acceptance: latency budget < 5 ms for 50 args ×
        50 markers. Locked in via a quick wall-clock probe — generous
        enough to absorb CI noise."""
        tracker = _tracker_with(*[f"CANARY-{i}" for i in range(50)])
        args: dict[str, str] = {f"arg_{i}": f"value-{i}" for i in range(50)}

        start = time.perf_counter()
        for _ in range(10):  # 10 runs to smooth jitter
            mediate_tool_arguments(args, tracker)
        elapsed_ms = (time.perf_counter() - start) * 1000 / 10

        assert elapsed_ms < 5.0, (
            f"mediation took {elapsed_ms:.2f}ms (budget 5ms)"
        )


class TestVerdictAttributes:
    def test_blocked_property(self) -> None:
        block = MediationVerdict(decision=MediationDecision.BLOCK)
        allow = MediationVerdict(decision=MediationDecision.ALLOW)
        assert block.blocked is True
        assert allow.blocked is False

    def test_verdict_is_frozen(self) -> None:
        verdict = MediationVerdict(decision=MediationDecision.ALLOW)
        try:
            verdict.decision = MediationDecision.BLOCK  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("MediationVerdict must be frozen")

    def test_taint_hit_is_frozen(self) -> None:
        from aegis.hardening.taint import TaintMarker

        hit = TaintHit(
            argument_path="x",
            marker=TaintMarker(value="y", source="z", level=TaintLevel.SECRET),
        )
        try:
            hit.argument_path = "changed"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("TaintHit must be frozen")
