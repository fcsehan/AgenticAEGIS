"""Tool-Argument disclosure mediation (AEGIS-1804, Epic 18).

Tool calls whose arguments carry tainted content (canary tokens,
classified strings) must not reach an external sink. This module
inspects the tool arguments before execution, looks them up against
the active ``TaintTracker``, and surfaces a structured decision.

Per AEGIS-1804 acceptance:

- Tool arguments with free-text payload are checked against the taint
  state before the tool runs.
- Tainted markers in arguments → BLOCK (the host contract turns this
  into a refusal at the host boundary, since hosts that only have
  preToolUse semantics cannot redact selectively).
- LLM-pipeline callers can inspect the structured ``MediationVerdict``
  and choose to redact rather than block.
- Latency budget: < 5 ms per check on a 50-arg × 50-marker workload —
  enforced by a property-style test in the test suite.

The mediation is **deterministic** and **does not call the LLM**. It is
a pure pattern-match defense-in-depth layer; the formal disclosure
guarantee belongs to Epic 19.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from aegis.hardening.taint import TaintMarker, TaintTracker


class MediationDecision(Enum):
    """Outcome of a tool-argument mediation check."""

    ALLOW = "ALLOW"
    """No taint detected; tool may proceed."""

    BLOCK = "BLOCK"
    """Taint detected; tool must NOT proceed. Host integrations that
    cannot redact selectively translate this to a refusal at the
    boundary (preToolUse hook returns deny). LLM-pipeline callers
    may choose to redact and retry."""


@dataclass(frozen=True, slots=True)
class TaintHit:
    """A single taint detection inside tool arguments."""

    argument_path: str
    """Dot-path inside the arguments dict, e.g. ``"message.body"``."""

    marker: TaintMarker
    """The taint marker that was found."""


@dataclass(frozen=True, slots=True)
class MediationVerdict:
    """Result of ``mediate_tool_arguments``."""

    decision: MediationDecision
    hits: tuple[TaintHit, ...] = ()
    channel_id: str = ""

    @property
    def blocked(self) -> bool:
        return self.decision == MediationDecision.BLOCK


def _walk_strings(payload: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Yield (path, string) pairs for every string-valued leaf in
    ``payload``. Recurses into dicts and lists/tuples; ignores other
    types because they cannot carry taint markers (which are strings).
    """
    if isinstance(payload, str):
        return [(prefix or "<root>", payload)]
    out: list[tuple[str, str]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_walk_strings(value, child_prefix))
    elif isinstance(payload, (list, tuple)):
        for idx, value in enumerate(payload):
            child_prefix = f"{prefix}[{idx}]"
            out.extend(_walk_strings(value, child_prefix))
    return out


def mediate_tool_arguments(
    arguments: dict[str, Any],
    tracker: TaintTracker,
    *,
    channel_id: str = "",
) -> MediationVerdict:
    """Inspect ``arguments`` for tainted strings and return a verdict.

    The check walks every string-valued leaf in the argument tree
    (recursing into dicts and lists). Each leaf is matched against
    the tracker's markers via ``TaintTracker.check`` (substring-based,
    classification-aware).

    Returns:
        ``MediationVerdict(decision=ALLOW)`` when no taint is detected.
        ``MediationVerdict(decision=BLOCK, hits=...)`` when at least
        one tainted string is present in any argument.

    Performance: O(n × m) with n = number of string leaves and
    m = number of taint markers. Tracker.check is O(m) per leaf.
    """
    hits: list[TaintHit] = []
    for path, value in _walk_strings(arguments):
        for marker in tracker.check(value):
            hits.append(TaintHit(argument_path=path, marker=marker))

    if hits:
        return MediationVerdict(
            decision=MediationDecision.BLOCK,
            hits=tuple(hits),
            channel_id=channel_id,
        )
    return MediationVerdict(
        decision=MediationDecision.ALLOW,
        channel_id=channel_id,
    )
