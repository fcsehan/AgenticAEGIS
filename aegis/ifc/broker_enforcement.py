"""Mandatory-broker-enforcement helpers (AEGIS-1803, Epic 18).

Closes the gap between *"the channel registry says broker is required"*
(AEGIS-1801 + AEGIS-1802) and *"the runtime actually used the broker"*.
Until this module landed, channels could declare ``requires_broker=True``
without the runtime enforcing it — a classified read could in principle
slip past the ``RetrievalBroker`` and reach the LLM directly.

Two complementary mechanisms:

1. ``BrokerCallLedger`` records every broker-mediated call by channel
   ID, action ID, and timestamp. The broker writes to it; the
   orchestrator and host integrations read from it.
2. ``assert_broker_mediated(channel_id, action_id)`` raises
   ``UnguardedRetrievalError`` when called for a channel that requires
   broker mediation but no matching ledger entry exists. The error
   carries the ``UNGUARDED_RETRIEVAL`` finding code for direct
   integration with the red-team scorecard (which already lists that
   code in ``BYPASS_FINDING_CODES``).

The ledger is per-session (per ``BrokerCallLedger`` instance), so
multi-tenant deployments can scope the enforcement window to a single
agent conversation.

Per AEGIS-1803 acceptance: ``searchCorpus`` and ``readDocument`` are
checked **separately** because they are distinct mappings (AEGIS-1802).
A broker call for ``readDocument`` does not satisfy a ``searchCorpus``
requirement.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock

from aegis.ifc.channel_action_mapping import ensure_mapping
from aegis.ifc.channel_registry import ensure_registered

UNGUARDED_RETRIEVAL_CODE = "UNGUARDED_RETRIEVAL"
"""Finding code used when a runtime path tried to retrieve through a
channel that required broker mediation, without going through the
broker. Already listed in ``BYPASS_FINDING_CODES``."""


@dataclass(frozen=True, slots=True)
class BrokerCall:
    """Record of one broker-mediated call.

    Attributes:
        channel_id: the registered channel that was traversed.
        action_type: the formal action_type the broker checked.
        action_id: stable identifier — typically the audit entry ID
            or a uuid the broker mints. Used by ``assert_broker_mediated``
            to match the most recent retrieval against the call ledger.
        timestamp: monotonic timestamp (``time.monotonic()``) so the
            ledger can support time-bounded freshness checks.
    """

    channel_id: str
    action_type: str
    action_id: str
    timestamp: float


class UnguardedRetrievalError(RuntimeError):
    """Raised when a channel that requires broker mediation was used
    without a matching broker call. Carries the
    ``UNGUARDED_RETRIEVAL`` finding code for scorecard integration."""

    code = UNGUARDED_RETRIEVAL_CODE

    def __init__(self, message: str, *, channel_id: str = "") -> None:
        super().__init__(message)
        self.channel_id = channel_id


@dataclass
class BrokerCallLedger:
    """Thread-safe in-memory ledger of broker-mediated calls.

    Each agent session owns one ledger; the broker writes to it during
    every ``broker_read`` / ``broker_search``, and the orchestrator
    consults it before letting a retrieval result reach the LLM.

    The ledger is intentionally tiny — append-only, no removal — so
    audit reconstructs the call sequence verbatim.
    """

    calls: list[BrokerCall] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def record(self, channel_id: str, action_type: str, action_id: str) -> BrokerCall:
        """Record a broker call. Returns the entry for further audit
        threading."""
        # Ensure the channel is registered. Unregistered channels are a
        # configuration error, not a runtime expectation.
        ensure_registered(channel_id)
        ensure_mapping(channel_id)

        call = BrokerCall(
            channel_id=channel_id,
            action_type=action_type,
            action_id=action_id,
            timestamp=time.monotonic(),
        )
        with self._lock:
            self.calls.append(call)
        return call

    def has_recent_call(
        self,
        channel_id: str,
        *,
        within_seconds: float = 5.0,
    ) -> bool:
        """True if a broker call for ``channel_id`` was recorded within
        ``within_seconds`` of now. The freshness window protects against
        stale ledger entries reused across requests."""
        cutoff = time.monotonic() - within_seconds
        with self._lock:
            for call in reversed(self.calls):
                if call.timestamp < cutoff:
                    break
                if call.channel_id == channel_id:
                    return True
        return False

    def has_call_for_action(self, channel_id: str, action_id: str) -> bool:
        """Strict lookup: a specific (channel, action) pair must be in
        the ledger. Used when the orchestrator wants to bind a single
        retrieval to a single broker call."""
        with self._lock:
            return any(
                c.channel_id == channel_id and c.action_id == action_id
                for c in self.calls
            )


def assert_broker_mediated(
    ledger: BrokerCallLedger,
    channel_id: str,
    *,
    action_id: str | None = None,
    within_seconds: float = 5.0,
) -> None:
    """Assert that ``channel_id`` was broker-mediated.

    Behaviour:

    - If the channel mapping declares ``mediation_type != BROKER`` and
      ``requires_broker == False``, the assertion is a no-op.
    - Otherwise:
      - if ``action_id`` is supplied, the ledger must contain that
        exact (channel, action) pair.
      - if ``action_id`` is None, a recent call for the channel within
        ``within_seconds`` is sufficient.
      - on miss, raises ``UnguardedRetrievalError`` carrying the
        ``UNGUARDED_RETRIEVAL`` finding code.

    AEGIS-1803 separates ``readDocument`` from ``searchCorpus``: a
    broker call for one does NOT satisfy the requirement for the
    other, because their channel IDs differ.
    """
    from aegis.ifc.channel_action_mapping import mapping_by_channel_id
    from aegis.ifc.channel_registry import channel_by_id

    channel = channel_by_id(channel_id)
    mapping = mapping_by_channel_id(channel_id)
    if channel is None or mapping is None:
        # ensure_registered / ensure_mapping raise their own errors;
        # here we just skip when the channel isn't broker-relevant.
        return

    if not channel.requires_broker:
        return

    if action_id is not None:
        if ledger.has_call_for_action(channel_id, action_id):
            return
        raise UnguardedRetrievalError(
            f"Channel {channel_id!r} requires broker mediation; no broker "
            f"call recorded for action_id={action_id!r}.",
            channel_id=channel_id,
        )

    if ledger.has_recent_call(channel_id, within_seconds=within_seconds):
        return

    raise UnguardedRetrievalError(
        f"Channel {channel_id!r} requires broker mediation; no broker "
        f"call recorded within the last {within_seconds:.1f}s.",
        channel_id=channel_id,
    )
