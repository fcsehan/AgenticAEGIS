"""AEGIS-1808 + AEGIS-1801: Information Flow Channel Registry.

Formalizes every identified information flow channel through the AEGIS
perimeter.  Each channel is documented with its kind, direction, host
surface, mediation requirements, enforcement mechanism, and the
red-team scenarios that verify it.

New channels MUST be registered here.  HC-009 verifies that every
channel has at least one verifying scenario.

AEGIS-1801 (Epic 18) extends the original AEGIS-1808 schema with the
fields needed for the 100%-Guard-Claim coverage analysis:

- ``kind``           — what the channel transports
- ``direction``      — which way information flows
- ``host_surface``   — which host hook or endpoint exposes it
- ``requires_guard`` — whether a Guard.check is mandatory
- ``requires_broker``— whether the channel must be broker-mediated
- ``mediation_type`` — the formal mediation mechanism

Runtime helper ``ensure_registered`` enforces fail-closed:
unregistered channel IDs raise immediately rather than silently
slipping past the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChannelKind(Enum):
    """What an information flow channel transports.

    Per AEGIS-1801 acceptance criterion: the registry must classify
    channels into a small canonical set so coverage analyses
    (``aegis-redteam coverage``) can group them.
    """

    DISCOVERY = "discovery"
    """Channel that exposes the existence/metadata of resources
    (e.g. file listings, search results)."""

    RETRIEVAL = "retrieval"
    """Channel that returns the content of a resource
    (e.g. file reads, document fetches)."""

    TRANSFORMATION = "transformation"
    """Channel that consumes input and produces a derived artefact
    (e.g. summarisation, redaction)."""

    DISCLOSURE = "disclosure"
    """Channel that emits content beyond the AEGIS perimeter
    (e.g. final response to user, external message send)."""

    SIDE_EFFECT = "side_effect"
    """Channel that triggers a state change in the world
    (e.g. file write, external API call, deployment)."""


class ChannelDirection(Enum):
    """Direction of information flow across the channel."""

    INBOUND = "inbound"
    """Source outside the AEGIS perimeter, sink inside (e.g. tool result)."""

    OUTBOUND = "outbound"
    """Source inside, sink outside (e.g. final response)."""

    BIDIRECTIONAL = "bidirectional"
    """Some interactions flow both ways within a single channel
    (e.g. RPC-style tool calls)."""


class MediationType(Enum):
    """Formal mediation mechanism for the channel.

    Mirrors the four enforcement primitives of AEGIS:
    ``action_check`` for ``Guard.check``, ``broker`` for
    ``RetrievalBroker``, ``disclosure_gate`` for the
    formal-disclosure layer (Epic 19), ``output_guard`` for the
    pattern-based ``OutputFilter``.
    """

    ACTION_CHECK = "action_check"
    BROKER = "broker"
    DISCLOSURE_GATE = "disclosure_gate"
    OUTPUT_GUARD = "output_guard"


@dataclass(frozen=True, slots=True)
class InformationChannel:
    """A single information flow channel through the Guard perimeter.

    Attributes:
        channel_id: Unique identifier (e.g. ``"orchestrator_tool_result"``).
        description: Human-readable description of what flows through this channel.
        enforcement: Mechanism that guards this channel
            (``"broker"`` | ``"output_guard"`` | ``"pre_hook"`` | ``"action_check"``).
        guard_interposition: True if the Guard sits between source and sink.
        verified_by: Scenario IDs that test this channel.
        kind: AEGIS-1801 classification (``ChannelKind``).
        direction: AEGIS-1801 flow direction.
        host_surface: Which host-side surface exposes this channel
            (e.g. ``"opencode_tool_dispatcher"``,
            ``"sidecar_http_endpoint"``). Empty string when AEGIS-internal.
        requires_guard: True if a Guard.check is mandatory before
            data crosses this channel.
        requires_broker: True if the channel must be broker-mediated.
        mediation_type: The formal mediation mechanism. Defaults to
            ``ACTION_CHECK`` when ``requires_guard`` is True without
            broker requirement.
    """

    channel_id: str
    description: str
    enforcement: str
    guard_interposition: bool
    verified_by: tuple[str, ...]
    # AEGIS-1801 extensions, all with defaults so existing callers stay
    # backward-compatible until the registry is fully back-filled.
    kind: ChannelKind = ChannelKind.SIDE_EFFECT
    direction: ChannelDirection = ChannelDirection.BIDIRECTIONAL
    host_surface: str = ""
    requires_guard: bool = True
    requires_broker: bool = False
    mediation_type: MediationType = MediationType.ACTION_CHECK


# ── The 10 canonical information flow channels ────────────────────

CHANNEL_REGISTRY: tuple[InformationChannel, ...] = (
    InformationChannel(
        channel_id="orchestrator_tool_call",
        description="LLM proposes action → Guard checks before execution",
        enforcement="action_check",
        guard_interposition=True,
        verified_by=(
            "03_direct_user_override_requires_guard_or_refusal",
            "08_permit_replay_different_action",
        ),
        kind=ChannelKind.SIDE_EFFECT,
        direction=ChannelDirection.OUTBOUND,
        host_surface="orchestrator_tool_dispatcher",
        requires_guard=True,
        requires_broker=False,
        mediation_type=MediationType.ACTION_CHECK,
    ),
    InformationChannel(
        channel_id="orchestrator_tool_result",
        description="Tool execution result → LLM context (via broker)",
        enforcement="broker",
        guard_interposition=True,
        verified_by=(
            "11_broker_denies_secret_read",
            "13_search_classified_corpus",
            "22_broker_mandatory_no_fallback",
        ),
        kind=ChannelKind.RETRIEVAL,
        direction=ChannelDirection.INBOUND,
        host_surface="orchestrator_tool_dispatcher",
        requires_guard=True,
        requires_broker=True,
        mediation_type=MediationType.BROKER,
    ),
    InformationChannel(
        channel_id="orchestrator_final_response",
        description="LLM final text response → user (via OutputFilter)",
        enforcement="output_guard",
        guard_interposition=True,
        verified_by=(
            "01_public_summary_no_canary_leak",
            "05_partial_secret_fragment_reuse_detected",
            "23_output_guard_sidecar_blocks_leak",
        ),
        kind=ChannelKind.DISCLOSURE,
        direction=ChannelDirection.OUTBOUND,
        host_surface="orchestrator_final_text",
        requires_guard=True,
        requires_broker=False,
        mediation_type=MediationType.OUTPUT_GUARD,
    ),
    InformationChannel(
        channel_id="host_pretooluse",
        description="Host preToolUse hook → Guard check → allow/deny",
        enforcement="pre_hook",
        guard_interposition=True,
        verified_by=(
            "19_pretooluse_blocks_classified_read",
        ),
        kind=ChannelKind.SIDE_EFFECT,
        direction=ChannelDirection.OUTBOUND,
        host_surface="host_preToolUse",
        requires_guard=True,
        requires_broker=False,
        mediation_type=MediationType.ACTION_CHECK,
    ),
    InformationChannel(
        channel_id="host_posttooluse_audit",
        description="Host postToolUse audit hook (observational only)",
        enforcement="output_guard",
        guard_interposition=False,
        verified_by=(
            "17_taint_persistence_across_turns",
            "20_taint_propagation_cross_tool",
        ),
        kind=ChannelKind.RETRIEVAL,
        direction=ChannelDirection.INBOUND,
        host_surface="host_postToolUse",
        requires_guard=False,
        requires_broker=False,
        mediation_type=MediationType.OUTPUT_GUARD,
    ),
    InformationChannel(
        channel_id="sidecar_broker_read",
        description="Sidecar /v1/broker/read endpoint for host integration",
        enforcement="broker",
        guard_interposition=True,
        verified_by=(
            "18_sidecar_broker_denies_read",
        ),
        kind=ChannelKind.RETRIEVAL,
        direction=ChannelDirection.INBOUND,
        host_surface="sidecar_http_endpoint",
        requires_guard=True,
        requires_broker=True,
        mediation_type=MediationType.BROKER,
    ),
    InformationChannel(
        channel_id="external_tool_side_effect",
        description="Unguarded external tool (send_external_message)",
        enforcement="action_check",
        guard_interposition=True,
        verified_by=(
            "06_unguarded_external_tool_boundary",
            "12_summarize_secret_for_external",
        ),
        kind=ChannelKind.DISCLOSURE,
        direction=ChannelDirection.OUTBOUND,
        host_surface="external_tool_dispatcher",
        requires_guard=True,
        requires_broker=False,
        mediation_type=MediationType.ACTION_CHECK,
    ),
    InformationChannel(
        channel_id="taint_propagation",
        description="Taint state propagates across tool calls in session",
        enforcement="output_guard",
        guard_interposition=True,
        verified_by=(
            "17_taint_persistence_across_turns",
            "20_taint_propagation_cross_tool",
        ),
        kind=ChannelKind.TRANSFORMATION,
        direction=ChannelDirection.BIDIRECTIONAL,
        host_surface="taint_tracker",
        requires_guard=True,
        requires_broker=False,
        mediation_type=MediationType.OUTPUT_GUARD,
    ),
    InformationChannel(
        channel_id="classification_manifest",
        description="Workspace .aegis-classification.json drives pre-read blocking",
        enforcement="pre_hook",
        guard_interposition=True,
        verified_by=(
            "21_classification_manifest_enforcement",
        ),
        kind=ChannelKind.DISCOVERY,
        direction=ChannelDirection.INBOUND,
        host_surface="classification_manifest_loader",
        requires_guard=True,
        requires_broker=False,
        mediation_type=MediationType.ACTION_CHECK,
    ),
    InformationChannel(
        channel_id="search_aggregation",
        description="Search across multiple classified files → aggregation risk",
        enforcement="broker",
        guard_interposition=True,
        verified_by=(
            "15_multi_file_aggregation",
            "09_multi_step_exfiltration_via_search",
        ),
        kind=ChannelKind.DISCOVERY,
        direction=ChannelDirection.INBOUND,
        host_surface="search_dispatcher",
        requires_guard=True,
        requires_broker=True,
        mediation_type=MediationType.BROKER,
    ),
)


def uncovered_channels() -> list[InformationChannel]:
    """Return channels that have no verifying scenarios."""
    return [ch for ch in CHANNEL_REGISTRY if not ch.verified_by]


def channel_by_id(channel_id: str) -> InformationChannel | None:
    """Look up a channel by its identifier."""
    for ch in CHANNEL_REGISTRY:
        if ch.channel_id == channel_id:
            return ch
    return None


def all_verified_scenario_ids() -> set[str]:
    """Return the set of all scenario IDs referenced by the registry."""
    ids: set[str] = set()
    for ch in CHANNEL_REGISTRY:
        ids.update(ch.verified_by)
    return ids


class UnregisteredChannelError(ValueError):
    """Raised by ``ensure_registered`` when a runtime path tries to use
    a channel ID that is not in the canonical registry.

    AEGIS-1801 acceptance criterion: a channel without a registry entry
    must trigger fail-closed behaviour rather than silently slipping
    past the registry. Host integrations and runtime mediators call
    ``ensure_registered`` before any data flows.
    """


def ensure_registered(channel_id: str) -> InformationChannel:
    """Look up ``channel_id`` and return the entry, or raise.

    Use at runtime guards (broker, output filter, pretooluse) to assert
    that the channel is part of the canonical registry. Unknown channels
    surface as ``UnregisteredChannelError``.
    """
    channel = channel_by_id(channel_id)
    if channel is None:
        raise UnregisteredChannelError(
            f"Channel {channel_id!r} is not registered in CHANNEL_REGISTRY. "
            f"Add an InformationChannel entry to "
            f"aegis/ifc/channel_registry.py or use one of: "
            f"{sorted(c.channel_id for c in CHANNEL_REGISTRY)}",
        )
    return channel


def channels_by_kind(kind: ChannelKind) -> list[InformationChannel]:
    """Return all channels of a given ``ChannelKind`` (AEGIS-1801)."""
    return [ch for ch in CHANNEL_REGISTRY if ch.kind == kind]


def channels_requiring_broker() -> list[InformationChannel]:
    """Return all channels declared as ``requires_broker=True``.

    Used by the AEGIS-1803 mandatory-broker-enforcement check (Epic 18
    Wave 2): every such channel must in fact route through the broker
    at runtime.
    """
    return [ch for ch in CHANNEL_REGISTRY if ch.requires_broker]


def channels_requiring_guard() -> list[InformationChannel]:
    """Return all channels declared as ``requires_guard=True``."""
    return [ch for ch in CHANNEL_REGISTRY if ch.requires_guard]
