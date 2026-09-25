"""AuditTrail — hash-chained JSONL audit log writer.

Thread-safe, append-only, with file rotation at 100 MB.
Per D-005: threading.Lock on append only; entry construction is lock-free.
Per D-004: AuditWriteError is non-fatal (raised, caught by Guard).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aegis.audit.entry import AuditEntry, ReasoningStep
from aegis.errors import AuditWriteError
from aegis.guard.action import Action
from aegis.guard.verdict import Verdict

logger = logging.getLogger(__name__)

_GENESIS_HASH = hashlib.sha256(b"GENESIS").hexdigest()
_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
_SCHEMA_VERSION = 1


class AuditTrail:
    """Hash-chained JSONL audit trail.

    Usage::

        trail = AuditTrail(Path("audit.jsonl"))
        entry = trail.log(action, verdict)
        # entry.entry_hash chains to next entry's prev_hash
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._entry_counter = 0
        self._last_hash = _GENESIS_HASH

        # Resume from existing file if present
        if self._path.exists() and self._path.stat().st_size > 0:
            self._resume()

    def _resume(self) -> None:
        """Resume hash chain from existing JSONL file."""
        last_line: str | None = None
        with self._path.open("r") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_line = line

        if last_line is not None:
            try:
                data = json.loads(last_line)
                self._entry_counter = data["entry_id"] + 1
                self._last_hash = data["entry_hash"]
            except (json.JSONDecodeError, KeyError) as e:
                raise AuditWriteError(
                    f"Cannot resume from corrupt audit trail: {e}"
                ) from e

    def log(self, action: Action, verdict: Verdict) -> AuditEntry:
        """Log an ACTION_VERDICT event. Thread-safe.

        Raises:
            AuditWriteError: If the entry cannot be written (non-fatal per D-004).
        """
        # Prepare serializable data outside lock (pure computation)
        action_dict = _action_to_dict(action)
        verdict_dict = _verdict_to_dict(verdict)
        reasoning_chain = _verdict_to_reasoning(verdict)

        with self._lock:
            entry = self._build_entry(
                event="ACTION_VERDICT",
                action_dict=action_dict,
                verdict_dict=verdict_dict,
                reasoning_chain=reasoning_chain,
                details=None,
            )
            self._append(entry)
        return entry

    def log_event(self, event: str, details: dict[str, Any]) -> AuditEntry:
        """Log a non-verdict event (DOMAIN_RELOAD, INIT, etc.). Thread-safe.

        Raises:
            AuditWriteError: If the entry cannot be written.
        """
        with self._lock:
            entry = self._build_entry(
                event=event,
                action_dict=None,
                verdict_dict=None,
                reasoning_chain=(),
                details=details,
            )
            self._append(entry)
        return entry

    def log_confirmation(
        self,
        *,
        trigger_reasons: list[str],
        echo_format: str,
        principal: str,
        proposed_action_type: str,
        user_intent: str,
        confirmed: bool,
        response_time_ms: int,
        final_decision: str,
    ) -> AuditEntry:
        """Log a CONFIRMATION_LIFECYCLE event from the User-Confirmation-Loop
        (Epic 33, AEGIS-3306).

        Captures the full lifecycle of one confirmation prompt:
        - what triggered it (trigger_reasons)
        - how the prompt was rendered (echo_format)
        - who answered and how long they took (principal, response_time_ms)
        - whether they confirmed (confirmed, final_decision)

        ``response_time_ms < 1000`` is annotated as ``FAST_CONFIRMATION``
        so dashboards can spot consent-theater patterns (the audit
        downstream stats CLI flags accumulating fast-confirmations as
        a UX-quality signal).
        """
        details: dict[str, Any] = {
            "trigger_reasons": list(trigger_reasons),
            "echo_format": echo_format,
            "principal": principal,
            "proposed_action_type": proposed_action_type,
            "user_intent": user_intent,
            "confirmed": confirmed,
            "response_time_ms": response_time_ms,
            "final_decision": final_decision,
        }
        if response_time_ms < 1_000:
            details["fast_confirmation"] = True

        with self._lock:
            entry = self._build_entry(
                event="CONFIRMATION_LIFECYCLE",
                action_dict=None,
                verdict_dict=None,
                reasoning_chain=(),
                details=details,
            )
            self._append(entry)
        return entry

    def log_candidate_evaluation(
        self,
        actions: list[Action],
        per_candidate_verdicts: list[Verdict],
        chosen: Verdict,
        minimal_candidates: tuple[str, ...],
        *,
        user_intent: str | None = None,
    ) -> AuditEntry:
        """Log a CANDIDATE_EVALUATION event from ``Guard.check_candidates``
        (Epic 32, AEGIS-3205).

        The event captures every candidate's action+verdict pair plus
        the antichain of minimal PERMITTED candidates and the
        deterministic tie-break choice. Auditors reconstruct *why* one
        candidate was preferred over another from this single record.
        """
        candidates_payload: list[dict[str, Any]] = []
        for action, verdict in zip(actions, per_candidate_verdicts, strict=True):
            candidates_payload.append(
                {
                    "action": _action_to_dict(action),
                    "verdict": _verdict_to_dict(verdict),
                }
            )
        details: dict[str, Any] = {
            "candidates": candidates_payload,
            "minimal_candidates": list(minimal_candidates),
            "chosen_action_type": chosen.action_type,
            "chosen_decision": chosen.decision.value,
            "chosen_reason": chosen.reason_type.value,
        }
        if user_intent is not None:
            details["user_intent"] = user_intent

        with self._lock:
            entry = self._build_entry(
                event="CANDIDATE_EVALUATION",
                action_dict=None,
                verdict_dict=_verdict_to_dict(chosen),
                reasoning_chain=_verdict_to_reasoning(chosen),
                details=details,
            )
            self._append(entry)
        return entry

    def _build_entry(
        self,
        *,
        event: str,
        action_dict: dict[str, Any] | None,
        verdict_dict: dict[str, Any] | None,
        reasoning_chain: tuple[ReasoningStep, ...],
        details: dict[str, Any] | None,
    ) -> AuditEntry:
        """Construct an AuditEntry with computed hashes. Must be called under _lock."""
        entry_id = self._entry_counter
        prev_hash = self._last_hash

        timestamp = datetime.now(UTC).isoformat()

        # For non-verdict events, embed details in action_dict
        effective_action = action_dict if action_dict is not None else details

        partial = AuditEntry(
            entry_id=entry_id,
            event=event,
            schema_version=_SCHEMA_VERSION,
            timestamp=timestamp,
            action=effective_action,
            verdict=verdict_dict,
            reasoning_chain=reasoning_chain,
            domain_versions={},
            prev_hash=prev_hash,
            entry_hash="",  # placeholder
        )
        entry_hash = _compute_hash(partial.to_hashable_dict())

        return AuditEntry(
            entry_id=partial.entry_id,
            event=partial.event,
            schema_version=partial.schema_version,
            timestamp=partial.timestamp,
            action=partial.action,
            verdict=partial.verdict,
            reasoning_chain=partial.reasoning_chain,
            domain_versions=partial.domain_versions,
            prev_hash=partial.prev_hash,
            entry_hash=entry_hash,
        )

    def _append(self, entry: AuditEntry) -> None:
        """Append entry as JSONL line. Must be called under _lock."""
        try:
            if self._path.exists() and self._path.stat().st_size >= _MAX_FILE_SIZE:
                self._rotate()

            with self._path.open("a") as f:
                line = json.dumps(entry.to_dict(), separators=(",", ":"))
                f.write(line + "\n")

            self._entry_counter = entry.entry_id + 1
            self._last_hash = entry.entry_hash

        except OSError as e:
            raise AuditWriteError(f"Failed to write audit entry: {e}") from e

    def _rotate(self) -> None:
        """Rotate audit file: audit.jsonl → audit.jsonl.1, etc."""
        # Find next available rotation number
        n = 1
        while True:
            rotated = self._path.with_suffix(f"{self._path.suffix}.{n}")
            if not rotated.exists():
                break
            n += 1

        self._path.rename(rotated)
        logger.info("Rotated audit trail to %s", rotated)


def _compute_hash(entry_dict: dict[str, Any]) -> str:
    """SHA-256 of canonical JSON (sorted keys, compact separators)."""
    canonical = json.dumps(entry_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _action_to_dict(action: Action) -> dict[str, Any]:
    """Serialize an Action to a dict for audit.

    AEGIS-3003 (Epic 30): when ``user_intent`` is set, it is persisted
    next to the action so an auditor can reconstruct *why* this action
    was passed to the Guard. Records without ``user_intent`` remain
    backward-compatible — readers that ignore unknown keys still work.
    """
    payload: dict[str, Any] = {
        "action_type": action.action_type,
        "agent_id": action.agent_id,
        "proposition": action.proposition,
        "context": action.context,
    }
    if action.user_intent is not None:
        payload["user_intent"] = action.user_intent
    return payload


def _verdict_to_dict(verdict: Verdict) -> dict[str, Any]:
    """Serialize a Verdict to a dict for audit."""
    return {
        "decision": verdict.decision.value,
        "reason_type": verdict.reason_type.value,
        "justification_chain": list(verdict.justification_chain),
        "norms_applied": list(verdict.norms_applied),
        "action_type": verdict.action_type,
        "agent_id": verdict.agent_id,
    }


def _verdict_to_reasoning(verdict: Verdict) -> tuple[ReasoningStep, ...]:
    """Extract reasoning steps from a Verdict's justification chain."""
    steps: list[ReasoningStep] = []
    for justification in verdict.justification_chain:
        steps.append(
            ReasoningStep(
                step_type="DECISION" if not steps else "NORM_MATCHED",
                description=justification,
            )
        )
    if verdict.norms_applied:
        for norm in verdict.norms_applied:
            steps.append(
                ReasoningStep(
                    step_type="NORM_MATCHED",
                    description=f"Applied norm: {norm}",
                    details={"norm_source": norm},
                )
            )
    return tuple(steps)
