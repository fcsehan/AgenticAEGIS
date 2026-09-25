"""AuditEntry and ReasoningStep — the data model for audit trail entries.

Each Guard.check() produces an AuditEntry with a hash-chained integrity
guarantee (I3, I6).  ReasoningStep captures individual steps in the
DDIC evaluation for full traceability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ReasoningStep:
    """A single step in the DDIC reasoning chain.

    Attributes:
        step_type: Classification of the step (e.g. NORM_MATCHED, DECISION).
        description: Human-readable description of what happened.
        details: Structured data for machine consumption.
    """

    step_type: str
    description: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_type": self.step_type,
            "description": self.description,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReasoningStep:
        return cls(
            step_type=d["step_type"],
            description=d["description"],
            details=d.get("details", {}),
        )


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """A single audit trail entry with hash-chain integrity.

    Attributes:
        entry_id: Monotonically increasing sequence number.
        event: Event type (ACTION_VERDICT, DOMAIN_RELOAD, INIT, etc.).
        schema_version: Always 1 for v1.0 (D-008).
        timestamp: ISO 8601 UTC timestamp.
        action: Serialized Action, or None for non-verdict events.
        verdict: Serialized Verdict, or None for non-verdict events.
        reasoning_chain: Ordered reasoning steps from DDIC evaluation.
        domain_versions: Map of domain name → version/hash.
        prev_hash: SHA-256 hex of the previous entry's entry_hash.
        entry_hash: SHA-256 hex of this entry (computed over all other fields).
    """

    entry_id: int
    event: str
    schema_version: int
    timestamp: str
    action: dict[str, Any] | None
    verdict: dict[str, Any] | None
    reasoning_chain: tuple[ReasoningStep, ...]
    domain_versions: dict[str, str]
    prev_hash: str
    entry_hash: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output.

        Includes all fields. For hash computation, use to_hashable_dict()
        which excludes entry_hash.
        """
        return {
            "entry_id": self.entry_id,
            "event": self.event,
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "action": self.action,
            "verdict": self.verdict,
            "reasoning_chain": [s.to_dict() for s in self.reasoning_chain],
            "domain_versions": self.domain_versions,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }

    def to_hashable_dict(self) -> dict[str, Any]:
        """Serialize to dict for hash computation (excludes entry_hash)."""
        d = self.to_dict()
        del d["entry_hash"]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AuditEntry:
        return cls(
            entry_id=d["entry_id"],
            event=d["event"],
            schema_version=d["schema_version"],
            timestamp=d["timestamp"],
            action=d.get("action"),
            verdict=d.get("verdict"),
            reasoning_chain=tuple(
                ReasoningStep.from_dict(s) for s in d.get("reasoning_chain", ())
            ),
            domain_versions=d.get("domain_versions", {}),
            prev_hash=d["prev_hash"],
            entry_hash=d["entry_hash"],
        )

    def explain(self) -> str:
        """Human-readable explanation of this audit entry."""
        lines = [
            f"Entry #{self.entry_id} [{self.event}]",
            f"  Time: {self.timestamp}",
        ]
        if self.verdict:
            lines.append(f"  Decision: {self.verdict.get('decision', '?')}")
            lines.append(f"  Reason: {self.verdict.get('reason_type', '?')}")
        if self.action:
            lines.append(
                f"  Action: {self.action.get('action_type', '?')} "
                f"by {self.action.get('agent_id', '?')}"
            )
        if self.reasoning_chain:
            lines.append("  Reasoning:")
            for step in self.reasoning_chain:
                lines.append(f"    [{step.step_type}] {step.description}")
        lines.append(f"  Hash: {self.entry_hash[:16]}...")
        return "\n".join(lines)
