"""AEGIS-1502 / AEGIS-1706: Output Filter (Final-Response-Safety-Layer).

Checks LLM final text responses for canary tokens, classification markers,
and other sensitive patterns before they reach the user.

AEGIS-1706 adds classification-aware checking: when a session is tainted
(non-public content has been accessed), the output filter can enforce
disclosure restrictions based on the taint tracker state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aegis.hardening.taint import TaintTracker

_DEFAULT_MARKERS: list[str] = [
    "SECRET",
    "CLASSIFIED",
    "TOP SECRET",
    "CANARY:",
]

_SAFE_BLOCK_MESSAGE = (
    "This response has been blocked by the AEGIS output guard "
    "because it contained sensitive content."
)


@dataclass(frozen=True, slots=True)
class OutputCheckResult:
    """Result of checking LLM output text."""

    safe: bool
    redacted_text: str
    violations: tuple[str, ...] = ()
    blocked_markers: tuple[str, ...] = ()


class OutputFilter:
    """Final-response safety layer that detects sensitive content in text.

    Modes:
        ``"block"``: replaces the entire response with a safe message.
        ``"redact"``: replaces matched substrings with ``[REDACTED]``.
    """

    def __init__(self, *, mode: str = "block") -> None:
        if mode not in ("block", "redact"):
            raise ValueError(f"mode must be 'block' or 'redact', got {mode!r}")
        self._mode = mode
        self._markers: list[str] = list(_DEFAULT_MARKERS)
        self._patterns: list[re.Pattern[str]] = []

    def add_markers(self, markers: list[str]) -> None:
        """Add runtime-discovered sensitive markers."""
        for marker in markers:
            if marker and marker not in self._markers:
                self._markers.append(marker)

    def add_patterns(self, patterns: list[re.Pattern[str]]) -> None:
        """Add regex patterns to check against."""
        self._patterns.extend(patterns)

    def check_with_taint(
        self,
        text: str,
        taint_tracker: TaintTracker,
        *,
        recipient: str = "user",
        purpose: str = "response",
    ) -> OutputCheckResult:
        """Check *text* with taint-aware disclosure enforcement.

        1. Feed taint markers to self (dynamic markers from session).
        2. Run standard marker/pattern check.
        3. If the session is tainted and disclosure is not allowed for
           the given recipient/purpose, block regardless of marker hits.
        """
        # Step 1: Feed taint markers
        taint_tracker.feed_to_output_guard(self)

        # Step 2: Standard check
        result = self.check(text)

        # Step 3: Taint-based disclosure check
        if not result.safe:
            return result

        if taint_tracker.is_tainted():
            if not taint_tracker.check_disclosure_allowed(recipient, purpose):
                return OutputCheckResult(
                    safe=False,
                    redacted_text=_SAFE_BLOCK_MESSAGE,
                    violations=(
                        f"Tainted session (highest={taint_tracker.highest_classification.value}) "
                        f"— disclosure to {recipient!r} for {purpose!r} not allowed.",
                    ),
                )

        return result

    def check(self, text: str) -> OutputCheckResult:
        """Check *text* for sensitive content.

        Returns an :class:`OutputCheckResult` indicating whether the text
        is safe and providing a sanitized version if not.
        """
        if not text:
            return OutputCheckResult(safe=True, redacted_text=text)

        violations: list[str] = []
        blocked: list[str] = []

        # Check string markers (case-sensitive exact substring)
        for marker in self._markers:
            if marker in text:
                violations.append(f"marker detected: {marker!r}")
                blocked.append(marker)

        # Check regex patterns
        for pattern in self._patterns:
            match = pattern.search(text)
            if match:
                violations.append(f"pattern matched: {pattern.pattern!r}")
                blocked.append(match.group())

        if not violations:
            return OutputCheckResult(safe=True, redacted_text=text)

        # Apply mode
        if self._mode == "block":
            return OutputCheckResult(
                safe=False,
                redacted_text=_SAFE_BLOCK_MESSAGE,
                violations=tuple(violations),
                blocked_markers=tuple(blocked),
            )

        # Redact mode — replace matched substrings
        redacted = text
        for marker in self._markers:
            if marker in redacted:
                redacted = redacted.replace(marker, "[REDACTED]")
        for pattern in self._patterns:
            redacted = pattern.sub("[REDACTED]", redacted)

        return OutputCheckResult(
            safe=False,
            redacted_text=redacted,
            violations=tuple(violations),
            blocked_markers=tuple(blocked),
        )
