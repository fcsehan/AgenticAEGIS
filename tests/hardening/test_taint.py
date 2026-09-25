"""Tests for AEGIS-1506: Taint Tracking."""

from __future__ import annotations

from aegis.hardening.output_guard import OutputFilter
from aegis.hardening.taint import TaintLevel, TaintTracker


class TestTaintTracker:
    def test_mark_and_check_exact_match(self) -> None:
        tracker = TaintTracker()
        tracker.mark(["CROWN-EMBER-7719"], source="briefing.txt", level=TaintLevel.SECRET)
        hits = tracker.check("The token is CROWN-EMBER-7719.")
        assert len(hits) == 1
        assert hits[0].value == "CROWN-EMBER-7719"
        assert hits[0].source == "briefing.txt"
        assert hits[0].level == TaintLevel.SECRET

    def test_no_match_returns_empty(self) -> None:
        tracker = TaintTracker()
        tracker.mark(["CROWN-EMBER-7719"], source="briefing.txt", level=TaintLevel.SECRET)
        hits = tracker.check("The weather is clear.")
        assert hits == []

    def test_multiple_sources(self) -> None:
        tracker = TaintTracker()
        tracker.mark(["CANARY-A"], source="file1.txt", level=TaintLevel.SECRET)
        tracker.mark(["CANARY-B"], source="file2.txt", level=TaintLevel.CONFIDENTIAL)
        hits = tracker.check("Found CANARY-A and CANARY-B.")
        assert len(hits) == 2

    def test_empty_values_ignored(self) -> None:
        tracker = TaintTracker()
        tracker.mark(["", "VALID"], source="source", level=TaintLevel.INTERNAL)
        assert len(tracker.markers) == 1

    def test_check_empty_text(self) -> None:
        tracker = TaintTracker()
        tracker.mark(["CANARY"], source="source", level=TaintLevel.SECRET)
        assert tracker.check("") == []

    def test_feed_to_output_guard(self) -> None:
        tracker = TaintTracker()
        tracker.mark(["CROWN-EMBER-7719"], source="briefing", level=TaintLevel.SECRET)

        guard = OutputFilter()
        tracker.feed_to_output_guard(guard)

        result = guard.check("Leaking CROWN-EMBER-7719 in text.")
        assert not result.safe
        assert "CROWN-EMBER-7719" in result.blocked_markers

    def test_deduplication(self) -> None:
        tracker = TaintTracker()
        tracker.mark(["CANARY"], source="file.txt", level=TaintLevel.SECRET)
        tracker.mark(["CANARY"], source="file.txt", level=TaintLevel.SECRET)
        assert len(tracker.markers) == 1

    def test_level_distinction(self) -> None:
        """Same value from same source but different levels are distinct markers."""
        tracker = TaintTracker()
        tracker.mark(["DATA"], source="file.txt", level=TaintLevel.INTERNAL)
        tracker.mark(["DATA"], source="file.txt", level=TaintLevel.SECRET)
        assert len(tracker.markers) == 2
