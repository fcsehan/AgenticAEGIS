"""AEGIS-1504: Permit Tokens.

Binds a PERMITTED verdict to the specific action it was issued for.
Single-use, time-limited, thread-safe.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass, replace
from typing import Any

from aegis.guard.action import Action

_DEFAULT_TTL = 30.0  # seconds


@dataclass(frozen=True, slots=True)
class PermitToken:
    """A single-use permit binding a verdict to an action.

    Attributes:
        token_id: 32 hex chars (``secrets.token_hex(16)``).
        action_hash: SHA-256 of the canonical action representation.
        issued_at: ``time.monotonic()`` at issuance.
        ttl_seconds: Validity window (default 30s).
        consumed: Whether this token has been used.
    """

    token_id: str
    action_hash: str
    issued_at: float
    ttl_seconds: float = _DEFAULT_TTL
    consumed: bool = False

    def is_expired(self) -> bool:
        """True if the token has exceeded its TTL."""
        return (time.monotonic() - self.issued_at) > self.ttl_seconds


def canonical_action_hash(action: Action) -> str:
    """Compute a deterministic SHA-256 hash for *action*.

    The canonical form sorts proposition keys to ensure determinism.
    """
    canonical: dict[str, Any] = {
        "action_type": action.action_type,
        "agent_id": action.agent_id,
        "proposition": _sort_recursive(action.proposition),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _sort_recursive(obj: Any) -> Any:
    """Recursively sort dict keys for deterministic serialization."""
    if isinstance(obj, dict):
        return {k: _sort_recursive(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_sort_recursive(item) for item in obj]
    return obj


class PermitStore:
    """Thread-safe store for single-use permit tokens.

    Usage::

        store = PermitStore()
        token = store.issue(action)
        # ... later, at execution time ...
        consumed = store.consume(token.token_id, action)
        if consumed is None:
            # Token invalid, expired, already used, or wrong action
    """

    def __init__(self, *, ttl_seconds: float = _DEFAULT_TTL) -> None:
        self._ttl = ttl_seconds
        self._tokens: dict[str, PermitToken] = {}
        self._lock = threading.Lock()

    def issue(self, action: Action) -> PermitToken:
        """Issue a new permit token for *action*."""
        token = PermitToken(
            token_id=secrets.token_hex(16),
            action_hash=canonical_action_hash(action),
            issued_at=time.monotonic(),
            ttl_seconds=self._ttl,
        )
        with self._lock:
            self._gc()
            self._tokens[token.token_id] = token
        return token

    def consume(self, token_id: str, action: Action) -> PermitToken | None:
        """Consume *token_id* if it matches *action* and is still valid.

        Returns the consumed token, or ``None`` if consumption fails.
        Fails if: token unknown, already consumed, expired, or action mismatch.
        """
        expected_hash = canonical_action_hash(action)

        with self._lock:
            token = self._tokens.get(token_id)
            if token is None:
                return None
            if token.consumed:
                return None
            if token.is_expired():
                del self._tokens[token_id]
                return None
            if token.action_hash != expected_hash:
                return None

            consumed = replace(token, consumed=True)
            self._tokens[token_id] = consumed
            return consumed

    def _gc(self) -> None:
        """Remove expired tokens. Must be called under lock."""
        expired = [
            tid for tid, tok in self._tokens.items()
            if tok.is_expired()
        ]
        for tid in expired:
            del self._tokens[tid]


# ── AEGIS-2711 (Epic 27): Plan-Permit-Tokens ────────────────────────


@dataclass(frozen=True, slots=True)
class PlanPermitToken:
    """A plan-level permit binding a verdict to a specific plan shape.

    Issued only when ``Guard.plan_check`` returns ``PlanDecision.PERMITTED``.
    The token carries a per-step hash tuple so the executor can verify
    that the step it is about to run is the same step the Guard saw.
    Any tampering — substituting an action, reordering steps, adding a
    step — flips at least one hash and is rejected at consumption.

    Attributes:
        token_id: 32 hex chars (``secrets.token_hex(16)``).
        plan_id: Stable identifier from the originating Plan.
        expected_step_hashes: One ``canonical_action_hash`` per step,
            in step order. The executor consumes one hash per
            ``consume_plan_step`` call.
        consumed_step_indices: Steps already consumed (frozenset of
            int) — prevents replay of an executed step.
        issued_at: ``time.monotonic()`` at issuance.
        ttl_seconds: Validity window (default 30s).
        invalidated: True once the token has been hard-invalidated by
            a runtime error or hash mismatch; further consumes fail
            even within TTL.
    """

    token_id: str
    plan_id: str
    expected_step_hashes: tuple[str, ...]
    consumed_step_indices: frozenset[int] = frozenset()
    issued_at: float = 0.0
    ttl_seconds: float = _DEFAULT_TTL
    invalidated: bool = False

    def is_expired(self) -> bool:
        return (time.monotonic() - self.issued_at) > self.ttl_seconds


class PlanPermitStore:
    """Thread-safe store for plan-level permit tokens.

    Separate from ``PermitStore`` because the consumption protocol is
    different — plan tokens carry per-step hashes and are consumed
    step-by-step, not in one shot.
    """

    def __init__(self, *, ttl_seconds: float = _DEFAULT_TTL) -> None:
        self._ttl = ttl_seconds
        self._tokens: dict[str, PlanPermitToken] = {}
        self._lock = threading.Lock()

    def issue(self, plan_id: str, step_hashes: tuple[str, ...]) -> PlanPermitToken:
        """Issue a new plan-permit token.

        ``plan_id`` is taken from the Plan; ``step_hashes`` is one
        ``canonical_action_hash`` per step in plan order.
        """
        token = PlanPermitToken(
            token_id=secrets.token_hex(16),
            plan_id=plan_id,
            expected_step_hashes=tuple(step_hashes),
            issued_at=time.monotonic(),
            ttl_seconds=self._ttl,
        )
        with self._lock:
            self._gc()
            self._tokens[token.token_id] = token
        return token

    def consume_plan_step(
        self,
        token_id: str,
        step_index: int,
        action: Action,
    ) -> PlanPermitToken | None:
        """Consume the ``step_index``-th step of a plan token.

        Returns the updated token on success, ``None`` on any of:
        - unknown / expired / invalidated token
        - step_index out of range or already consumed
        - action hash does not match the expected hash at step_index

        D-004 (fail-closed): a hash mismatch HARD-INVALIDATES the
        token; subsequent steps cannot be executed even if their
        hashes would match. This is the smuggling defence — once
        someone tries to substitute a step, the whole plan is dead.
        """
        expected_hash = canonical_action_hash(action)
        with self._lock:
            token = self._tokens.get(token_id)
            if token is None:
                return None
            if token.is_expired():
                del self._tokens[token_id]
                return None
            if token.invalidated:
                return None
            if step_index < 0 or step_index >= len(token.expected_step_hashes):
                return None
            if step_index in token.consumed_step_indices:
                return None
            if token.expected_step_hashes[step_index] != expected_hash:
                # Hard-invalidate: future consumes fail.
                self._tokens[token_id] = replace(token, invalidated=True)
                return None
            updated = replace(
                token,
                consumed_step_indices=token.consumed_step_indices | {step_index},
            )
            self._tokens[token_id] = updated
            return updated

    def invalidate(self, token_id: str) -> None:
        """Hard-invalidate a token (used on runtime executor error)."""
        with self._lock:
            token = self._tokens.get(token_id)
            if token is not None:
                self._tokens[token_id] = replace(token, invalidated=True)

    def get(self, token_id: str) -> PlanPermitToken | None:
        with self._lock:
            return self._tokens.get(token_id)

    def _gc(self) -> None:
        expired = [
            tid for tid, tok in self._tokens.items()
            if tok.is_expired()
        ]
        for tid in expired:
            del self._tokens[tid]
