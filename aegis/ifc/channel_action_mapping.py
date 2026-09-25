"""Channel-to-Action mapping table (AEGIS-1802, Epic 18).

Maps each registered channel to the formal ``action_type`` that the
Guard evaluates when data crosses the channel. Without this mapping a
channel cannot be guarded — the runtime would not know which deontic
norms apply.

Per AEGIS-1802 acceptance criteria:

- Every channel in ``CHANNEL_REGISTRY`` has exactly one mapping.
- The mapping declares: ``action_type``, the required proposition
  fields, and the allowed response mode (deny / metadata-only /
  redacted-snippet / full-content) for retrieval channels.
- ``searchCorpus`` and ``readDocument`` are *separate* mappings —
  they are different actions deontically.
- ``transformation`` and ``disclosure`` channels are *separate* —
  conflating them would let a transformation result leak via a
  disclosure path without an explicit disclosure check.
- Channels without mapping → fail-closed at runtime via
  ``ensure_mapping`` (analogous to ``ensure_registered``).
- Mapping table is testable, versioned, and stable across runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aegis.ifc.channel_registry import (
    CHANNEL_REGISTRY,
    InformationChannel,
)


class ResponseMode(Enum):
    """How the channel may return data when the Guard permits.

    ``DENY``: nothing is returned (the channel is information-egress
    only; Guard.check yields PERMIT/FORBID with no payload).

    ``METADATA_ONLY``: only structural metadata leaves the channel
    (e.g. file existence, size); never the body.

    ``REDACTED_SNIPPET``: a redacted excerpt (e.g. classification-
    aware snippet) is returned. The redaction step belongs to the
    broker.

    ``FULL_CONTENT``: the channel may return full content when the
    Guard permits.
    """

    DENY = "deny"
    METADATA_ONLY = "metadata_only"
    REDACTED_SNIPPET = "redacted_snippet"
    FULL_CONTENT = "full_content"


@dataclass(frozen=True, slots=True)
class ChannelActionMapping:
    """Maps a channel ID to its formal ``action_type`` and contract.

    Attributes:
        channel_id: matches ``InformationChannel.channel_id``.
        action_type: the Guard ``action_type`` that gates the channel.
        required_proposition: tuple of proposition keys the Guard
            expects on every check (e.g. ``("path",)`` for file reads).
            Empty when the action has no schema-required parameters.
        response_mode: which response payloads are allowed (per the
            ``RetrievalBroker`` contract from Epic 17).
    """

    channel_id: str
    action_type: str
    required_proposition: tuple[str, ...] = ()
    response_mode: ResponseMode = ResponseMode.DENY


class UnmappedChannelError(ValueError):
    """Raised by ``ensure_mapping`` when a registered channel has no
    Channel-to-Action entry. AEGIS-1802 fail-closed semantics."""


# ── The 10-entry mapping table ─────────────────────────────────────

CHANNEL_ACTION_MAPPING: tuple[ChannelActionMapping, ...] = (
    ChannelActionMapping(
        channel_id="orchestrator_tool_call",
        action_type="invokeTool",
        required_proposition=("tool_name",),
        response_mode=ResponseMode.DENY,
    ),
    ChannelActionMapping(
        channel_id="orchestrator_tool_result",
        action_type="readDocument",
        required_proposition=("path",),
        response_mode=ResponseMode.REDACTED_SNIPPET,
    ),
    ChannelActionMapping(
        channel_id="orchestrator_final_response",
        action_type="discloseFinalResponse",
        required_proposition=("recipient",),
        response_mode=ResponseMode.FULL_CONTENT,
    ),
    ChannelActionMapping(
        channel_id="host_pretooluse",
        action_type="invokeTool",
        required_proposition=("tool_name",),
        response_mode=ResponseMode.DENY,
    ),
    ChannelActionMapping(
        channel_id="host_posttooluse_audit",
        # Audit-only channel: still mapped to a no-op verb so the
        # registry contract holds, but with response_mode DENY because
        # this channel produces no return-payload to the LLM.
        action_type="auditToolResult",
        required_proposition=("tool_name",),
        response_mode=ResponseMode.DENY,
    ),
    ChannelActionMapping(
        channel_id="sidecar_broker_read",
        action_type="readDocument",
        required_proposition=("path",),
        response_mode=ResponseMode.REDACTED_SNIPPET,
    ),
    ChannelActionMapping(
        channel_id="external_tool_side_effect",
        action_type="sendExternalMessage",
        required_proposition=("recipient", "message"),
        response_mode=ResponseMode.DENY,
    ),
    ChannelActionMapping(
        channel_id="taint_propagation",
        action_type="propagateTaint",
        # Internal control-plane channel — no required proposition.
        required_proposition=(),
        response_mode=ResponseMode.METADATA_ONLY,
    ),
    ChannelActionMapping(
        channel_id="classification_manifest",
        # Discovery channel: lists classified resources by metadata.
        action_type="listClassifiedResources",
        required_proposition=(),
        response_mode=ResponseMode.METADATA_ONLY,
    ),
    ChannelActionMapping(
        channel_id="search_aggregation",
        # Distinct from readDocument — searchCorpus has different
        # deontic semantics (n-document aggregation risk) per the
        # AEGIS-1802 acceptance criterion.
        action_type="searchCorpus",
        required_proposition=("query",),
        response_mode=ResponseMode.METADATA_ONLY,
    ),
)


def mapping_by_channel_id(channel_id: str) -> ChannelActionMapping | None:
    """Look up a mapping by channel ID."""
    for m in CHANNEL_ACTION_MAPPING:
        if m.channel_id == channel_id:
            return m
    return None


def ensure_mapping(channel_id: str) -> ChannelActionMapping:
    """Look up the mapping for ``channel_id`` or raise.

    Use at runtime guards (broker, output filter, pretooluse) to assert
    that the channel has a Channel-to-Action mapping. Channels without
    a mapping are unguardable; an unmapped channel surface as an
    ``UnmappedChannelError`` (AEGIS-1802 fail-closed).
    """
    mapping = mapping_by_channel_id(channel_id)
    if mapping is None:
        raise UnmappedChannelError(
            f"Channel {channel_id!r} has no entry in CHANNEL_ACTION_MAPPING. "
            "Add a ChannelActionMapping in aegis/ifc/channel_action_mapping.py "
            "or this channel cannot be guarded.",
        )
    return mapping


def unmapped_channels() -> list[InformationChannel]:
    """Return registered channels that have no Channel-to-Action
    mapping. AEGIS-1802 acceptance: this list must always be empty."""
    mapped_ids = {m.channel_id for m in CHANNEL_ACTION_MAPPING}
    return [ch for ch in CHANNEL_REGISTRY if ch.channel_id not in mapped_ids]


def search_corpus_and_read_document_are_separate() -> bool:
    """Architectural invariant from AEGIS-1802: ``searchCorpus`` and
    ``readDocument`` must be modelled as distinct ``action_type``s,
    because n-document aggregation risk is deontically distinct from
    single-document retrieval.

    Surface as a tested predicate so the architectural guarantee is
    visible in the test report.
    """
    actions = {m.action_type for m in CHANNEL_ACTION_MAPPING}
    return "searchCorpus" in actions and "readDocument" in actions


def transformation_and_disclosure_are_separate() -> bool:
    """Architectural invariant: a transformation channel must not
    map to the same ``action_type`` as a disclosure channel. Conflating
    them lets a transformation result reach the disclosure surface
    without an explicit disclosure check (Epic 19 prerequisite)."""
    from aegis.ifc.channel_registry import ChannelKind, channel_by_id

    transformation_actions: set[str] = set()
    disclosure_actions: set[str] = set()
    for m in CHANNEL_ACTION_MAPPING:
        ch = channel_by_id(m.channel_id)
        if ch is None:
            continue
        if ch.kind == ChannelKind.TRANSFORMATION:
            transformation_actions.add(m.action_type)
        if ch.kind == ChannelKind.DISCLOSURE:
            disclosure_actions.add(m.action_type)
    return transformation_actions.isdisjoint(disclosure_actions)
