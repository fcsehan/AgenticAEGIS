"""Tests for AEGIS-1502: Output Guard."""

from __future__ import annotations

import re

from aegis.hardening.output_guard import OutputFilter


class TestOutputFilter:
    def test_clean_text_passes(self) -> None:
        guard = OutputFilter()
        result = guard.check("Weather is clear over the western corridor.")
        assert result.safe
        assert result.redacted_text == "Weather is clear over the western corridor."

    def test_empty_text_passes(self) -> None:
        guard = OutputFilter()
        result = guard.check("")
        assert result.safe

    def test_detect_secret_marker(self) -> None:
        guard = OutputFilter()
        result = guard.check("The data is SECRET and should not be shared.")
        assert not result.safe
        assert "SECRET" in result.blocked_markers

    def test_detect_classified_marker(self) -> None:
        guard = OutputFilter()
        result = guard.check("This is CLASSIFIED information.")
        assert not result.safe

    def test_detect_canary_prefix(self) -> None:
        guard = OutputFilter()
        result = guard.check("CANARY: CROWN-EMBER-7719")
        assert not result.safe

    def test_detect_top_secret(self) -> None:
        guard = OutputFilter()
        result = guard.check("This is TOP SECRET material.")
        assert not result.safe

    def test_block_mode_replaces_entire_response(self) -> None:
        guard = OutputFilter(mode="block")
        result = guard.check("The code is SECRET.")
        assert not result.safe
        assert "SECRET" not in result.redacted_text
        assert "blocked" in result.redacted_text.lower()

    def test_redact_mode_replaces_markers(self) -> None:
        guard = OutputFilter(mode="redact")
        result = guard.check("The data is SECRET and also CLASSIFIED.")
        assert not result.safe
        assert "[REDACTED]" in result.redacted_text
        assert "SECRET" not in result.redacted_text
        assert "CLASSIFIED" not in result.redacted_text

    def test_multiple_markers_detected(self) -> None:
        guard = OutputFilter()
        result = guard.check("SECRET data and CLASSIFIED info.")
        assert not result.safe
        assert len(result.violations) == 2

    def test_dynamic_add_markers(self) -> None:
        guard = OutputFilter()
        guard.add_markers(["CROWN-EMBER-7719"])
        result = guard.check("The token is CROWN-EMBER-7719.")
        assert not result.safe
        assert "CROWN-EMBER-7719" in result.blocked_markers

    def test_add_markers_deduplicates(self) -> None:
        guard = OutputFilter()
        guard.add_markers(["CUSTOM-TOKEN"])
        guard.add_markers(["CUSTOM-TOKEN"])
        # Should not add duplicate
        assert guard._markers.count("CUSTOM-TOKEN") == 1

    def test_regex_patterns(self) -> None:
        guard = OutputFilter()
        guard.add_patterns([re.compile(r"CANARY-[A-Z]+-\d+")])
        result = guard.check("Found CANARY-ALPHA-1234 in the text.")
        assert not result.safe

    def test_redact_mode_with_regex(self) -> None:
        guard = OutputFilter(mode="redact")
        guard.add_patterns([re.compile(r"\b\d{3}-\d{2}-\d{4}\b")])
        result = guard.check("SSN: 123-45-6789 is private.")
        assert not result.safe
        assert "[REDACTED]" in result.redacted_text
        assert "123-45-6789" not in result.redacted_text

    def test_invalid_mode_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="mode must be"):
            OutputFilter(mode="invalid")
