"""Formal Disclosure-Action builder (AEGIS-1901..1904, Epic 19).

Promotes every effective output surface — final response, tool
arguments, transformation outputs — from "after-the-fact pattern-
matched filter" to "before-the-fact formal Guard.check action".

The motivation is the FINAL_RESPONSE_LEAK pattern observed in the
Copilot-CLI red-team runs: a deterministic ``OutputFilter`` catches
exact-string canaries but cannot reason about semantic content. By
modelling the disclosure as a formal action, the existing DDIC engine
(with its full norm corpus) decides — not a regex.

Per AEGIS-1901 acceptance the disclosure action carries:

- ``recipient`` (from host config, **never** LLM self-attestation —
  this defeats RR-002 by construction)
- ``purpose`` (from host config or conservative default)
- ``sourceClassification`` (highest TaintTracker level in the session)
- ``channel_id`` (from the canonical channel registry)

AEGIS-1902 reuses the same builder for tool-argument disclosures:
the action_type is identical, only ``recipient`` changes (the tool
sink rather than the user). This is the unification the spec calls
for: tool arguments are disclosure surfaces, not secondary channels.

AEGIS-1903 threads ``transformation_type`` through, so a ``summarize``
disclosure is deontically distinct from a ``compare`` disclosure
even when source classification is identical.

AEGIS-1904 surfaces the disclosure metadata in API responses and the
audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from aegis.guard.action import Action
from aegis.hardening.taint import TaintLevel, TaintTracker
from aegis.ifc.channel_action_mapping import (
    ChannelActionMapping,
    ensure_mapping,
)
from aegis.ifc.channel_registry import (
    InformationChannel,
    ensure_registered,
)


class TransformationType(Enum):
    """Canonical transformation types per AEGIS-1903.

    A transformation is anything that consumes input and produces a
    derived artefact. The type is part of the disclosure action
    proposition because deontic norms can distinguish "summarize my
    classified file" (often allowed) from "compare two classified
    files" (often forbidden — aggregation risk).
    """

    NONE = "none"
    """No transformation; disclosure flows raw."""

    SUMMARIZE = "summarize"
    EXTRACT = "extract"
    COMPARE = "compare"
    RANK = "rank"
    TRANSLATE = "translate"
    RECLASSIFY = "reclassify"


# Conservative recipient default for hosts that do not declare one.
# Picked so a misconfigured host fails closed at the disclosure check
# rather than silently labelling everything as ``self``.
_FALLBACK_RECIPIENT = "unspecified_recipient"
_FALLBACK_PURPOSE = "unspecified_purpose"


@dataclass(frozen=True, slots=True)
class DisclosureContext:
    """Inputs to ``build_disclosure_action`` — everything the host must
    provide so the formal action can be evaluated.

    Attributes:
        channel_id: must be in the canonical CHANNEL_REGISTRY.
        recipient: the host-declared recipient (NOT an LLM-supplied
            value). The host knows whether the sink is the user, an
            external API, a tool argument, etc.
        purpose: the host-declared intent for the disclosure (e.g.
            ``"final_user_response"``, ``"internalAnalysis"``).
        agent_id: the agent proposing the disclosure.
        transformation_type: one of TransformationType.
        provenance_sources: source paths or identifiers contributing
            to the artefact, threaded through transformations
            (AEGIS-1903).
    """

    channel_id: str
    recipient: str = _FALLBACK_RECIPIENT
    purpose: str = _FALLBACK_PURPOSE
    agent_id: str = ""
    transformation_type: TransformationType = TransformationType.NONE
    provenance_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DisclosureMetadata:
    """Structured payload returned alongside the Verdict (AEGIS-1904).

    Surfaced on API responses and persisted next to the audit entry so
    operators can prove that a disclosure check actually ran.
    """

    disclosure_checked: bool
    disclosure_action_type: str
    disclosure_decision: str
    channel_id: str
    transformation_type: str
    source_classification: str
    recipient: str
    purpose: str
    provenance_sources: tuple[str, ...] = field(default_factory=tuple)
    block_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "disclosure_checked": self.disclosure_checked,
            "disclosure_action_type": self.disclosure_action_type,
            "disclosure_decision": self.disclosure_decision,
            "channel_id": self.channel_id,
            "transformation_type": self.transformation_type,
            "source_classification": self.source_classification,
            "recipient": self.recipient,
            "purpose": self.purpose,
            "provenance_sources": list(self.provenance_sources),
            "block_reason": self.block_reason,
        }


_TAINT_RANK: dict[TaintLevel, int] = {
    TaintLevel.PUBLIC: 0,
    TaintLevel.INTERNAL: 1,
    TaintLevel.CONFIDENTIAL: 2,
    TaintLevel.SECRET: 3,
}


def _highest_classification(tracker: TaintTracker | None) -> str:
    """Return the highest classification touched in the session, or
    ``"public"`` when no tracker is supplied. The string mirrors the
    TaintLevel enum value so deontic norms can match on it.

    We consider two signals:

    1. ``tracker.highest_classification`` — reflects classifications
       fed via ``ingest_provenance`` (the broker path).
    2. ``tracker.markers[*].level`` — reflects values fed via
       ``mark`` (direct taint registration without a provenance
       result).

    Take the strictest of the two so a session that registered a
    SECRET marker via ``mark`` doesn't pretend to be public.
    """
    if tracker is None:
        return TaintLevel.PUBLIC.value.lower()
    best = tracker.highest_classification
    best_rank = _TAINT_RANK.get(best, 0)
    for marker in tracker.markers:
        rank = _TAINT_RANK.get(marker.level, 0)
        if rank > best_rank:
            best = marker.level
            best_rank = rank
    return best.value.lower()


def build_disclosure_action(
    context: DisclosureContext,
    tracker: TaintTracker | None = None,
) -> tuple[Action, ChannelActionMapping, InformationChannel]:
    """Build a formal disclosure ``Action`` from the host context.

    The function:

    1. Resolves the channel and the channel-action mapping (fail-closed
       when missing — propagates ``UnregisteredChannelError`` /
       ``UnmappedChannelError``).
    2. Reads the highest classification from the TaintTracker so the
       Guard sees the most-restrictive level. Empty tracker → public.
    3. Emits a single ``Action`` whose proposition contains the four
       AEGIS-1901 fields plus ``transformation_type`` (AEGIS-1903).

    Returns the Action plus the channel and mapping it was built
    against, so the caller can compose the verdict-handling without a
    second registry lookup.
    """
    channel = ensure_registered(context.channel_id)
    mapping = ensure_mapping(context.channel_id)

    proposition: dict[str, object] = {
        "recipient": context.recipient,
        "purpose": context.purpose,
        "sourceClassification": _highest_classification(tracker),
        "channel_id": context.channel_id,
        "transformation_type": context.transformation_type.value,
    }
    if context.provenance_sources:
        proposition["provenance_sources"] = list(context.provenance_sources)

    action = Action(
        action_type=mapping.action_type,
        agent_id=context.agent_id,
        proposition=proposition,
    )
    return action, mapping, channel


def disclosure_metadata_from(
    context: DisclosureContext,
    tracker: TaintTracker | None,
    *,
    decision: str,
    block_reason: str = "",
) -> DisclosureMetadata:
    """Project the disclosure context + Verdict into the public
    metadata payload (AEGIS-1904).

    Used by the orchestrator after Guard.check to attach the metadata
    to API responses and audit entries. The mapping lookup is shared
    with ``build_disclosure_action`` so the two sides cannot drift.
    """
    mapping = ensure_mapping(context.channel_id)
    return DisclosureMetadata(
        disclosure_checked=True,
        disclosure_action_type=mapping.action_type,
        disclosure_decision=decision,
        channel_id=context.channel_id,
        transformation_type=context.transformation_type.value,
        source_classification=_highest_classification(tracker),
        recipient=context.recipient,
        purpose=context.purpose,
        provenance_sources=context.provenance_sources,
        block_reason=block_reason,
    )


def transformation_type_from_string(value: str) -> TransformationType:
    """Tolerant string → TransformationType conversion.

    Domain authors and host integrations pass strings on the wire; we
    map case-insensitive matches and fall back to NONE for anything
    unknown (the orchestrator can layer a stricter rejection on top
    when it wants).
    """
    norm = value.strip().lower()
    for member in TransformationType:
        if member.value == norm:
            return member
    return TransformationType.NONE
