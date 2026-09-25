"""AEGIS-1406: Production Release Gate.

5 preconditions must be met before a domain can be released for production:
1. ALL_RULES_PARSED     — every rule passes syntax verification
2. ALL_SYMBOLS_VALID    — no unknown symbols
3. ALL_CONFLICTS_RESOLVED — no unresolved conflicts
4. ALL_TESTS_PASSED     — all functional tests passed
5. LEGAL_DOC_GENERATED  — legal document generated at least once

Only when all 5 are satisfied can the domain be published.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from aegis.audit.trail import AuditTrail
from aegis.editor.domain_model import DomainInfo
from aegis.editor.governance import GovernanceManager
from aegis.editor.meld_writer import export_domain
from aegis.errors import AuditWriteError

logger = logging.getLogger(__name__)


class PreConditionId(Enum):
    ALL_RULES_PARSED = "ALL_RULES_PARSED"
    ALL_SYMBOLS_VALID = "ALL_SYMBOLS_VALID"
    ALL_CONFLICTS_RESOLVED = "ALL_CONFLICTS_RESOLVED"
    ALL_TESTS_PASSED = "ALL_TESTS_PASSED"
    LEGAL_DOC_GENERATED = "LEGAL_DOC_GENERATED"


@dataclass
class ReleasePreCondition:
    """A single release precondition with its current status."""

    id: PreConditionId
    label: str
    satisfied: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id.value,
            "label": self.label,
            "satisfied": self.satisfied,
            "detail": self.detail,
        }


@dataclass
class ReleaseState:
    """Tracks authoring session state for release gate evaluation."""

    syntax_verified_rules: int = 0
    total_rules: int = 0
    symbol_verified_rules: int = 0
    unresolved_conflicts: int = 0
    functional_tests_passed: int = 0
    functional_tests_total: int = 0
    legal_doc_generated: bool = False
    legal_doc_hash: str = ""

    # Authoring metadata
    provider_id: str = ""
    model_id: str = ""
    rules_generated: int = 0
    rules_accepted: int = 0


@dataclass
class ReleaseResult:
    """Result of a release operation."""

    success: bool
    version: str = ""
    exported_files: list[str] = field(default_factory=list)
    audit_entry_id: int | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": self.success,
            "version": self.version,
            "exportedFiles": self.exported_files,
        }
        if self.audit_entry_id is not None:
            result["auditEntryId"] = self.audit_entry_id
        if self.error:
            result["error"] = self.error
        return result


class ReleaseGate:
    """Evaluates preconditions and manages production release.

    Usage::

        gate = ReleaseGate(domain, state)
        preconditions = gate.check_preconditions()
        if gate.can_release():
            result = gate.release(
                governance=mgr,
                output_dir=Path("./domains"),
                version="1.0.0",
            )
    """

    def __init__(self, domain: DomainInfo, state: ReleaseState) -> None:
        self._domain = domain
        self._state = state

    def check_preconditions(self) -> list[ReleasePreCondition]:
        """Evaluate all 5 preconditions and return their status."""
        s = self._state
        total = s.total_rules or len(self._domain.rules)

        return [
            ReleasePreCondition(
                id=PreConditionId.ALL_RULES_PARSED,
                label="All rules pass syntax verification",
                satisfied=s.syntax_verified_rules >= total > 0,
                detail=f"{s.syntax_verified_rules}/{total} rules verified",
            ),
            ReleasePreCondition(
                id=PreConditionId.ALL_SYMBOLS_VALID,
                label="All symbols are valid",
                satisfied=s.symbol_verified_rules >= total > 0,
                detail=f"{s.symbol_verified_rules}/{total} symbols validated",
            ),
            ReleasePreCondition(
                id=PreConditionId.ALL_CONFLICTS_RESOLVED,
                label="No unresolved conflicts",
                satisfied=s.unresolved_conflicts == 0,
                detail=(
                    "No conflicts"
                    if s.unresolved_conflicts == 0
                    else f"{s.unresolved_conflicts} unresolved conflict(s)"
                ),
            ),
            ReleasePreCondition(
                id=PreConditionId.ALL_TESTS_PASSED,
                label="All functional tests passed",
                satisfied=(
                    s.functional_tests_passed >= s.functional_tests_total > 0
                ),
                detail=f"{s.functional_tests_passed}/{s.functional_tests_total} tests passed",
            ),
            ReleasePreCondition(
                id=PreConditionId.LEGAL_DOC_GENERATED,
                label="Legal document generated",
                satisfied=s.legal_doc_generated,
                detail=(
                    f"SHA-256: {s.legal_doc_hash[:16]}..."
                    if s.legal_doc_hash
                    else "Not yet generated"
                ),
            ),
        ]

    def can_release(self) -> bool:
        """Return True if all preconditions are satisfied."""
        return all(pc.satisfied for pc in self.check_preconditions())

    def release(
        self,
        *,
        governance: GovernanceManager,
        output_dir: Path,
        version: str,
        message: str = "",
        audit_trail: AuditTrail | None = None,
    ) -> ReleaseResult:
        """Execute the release: export, publish, audit.

        Args:
            governance: GovernanceManager for publish workflow.
            output_dir: Directory for exported .meld files.
            version: Semantic version string.
            message: Optional release message.
            audit_trail: Optional audit trail for logging.

        Returns:
            ReleaseResult with status and details.
        """
        if not self.can_release():
            unmet = [
                pc.id.value
                for pc in self.check_preconditions()
                if not pc.satisfied
            ]
            return ReleaseResult(
                success=False,
                error=f"Preconditions not met: {', '.join(unmet)}",
            )

        try:
            # 1. Export domain to .meld files
            paths = export_domain(self._domain, output_dir)
            exported = [str(p) for p in paths]

            # 2. Publish via governance workflow
            gov = governance.get_or_create(self._domain.id)
            if gov.status == "Draft":
                governance.submit_for_review(self._domain.id, message=message)
            governance.publish(self._domain.id, version, message=message)

            # 3. Audit entry
            audit_entry_id: int | None = None
            if audit_trail is not None:
                try:
                    entry = audit_trail.log_event("LLM_AUTHORED_RELEASE", {
                        "domain_id": self._domain.id,
                        "version": version,
                        "provider_id": self._state.provider_id,
                        "model_id": self._state.model_id,
                        "rules_generated": self._state.rules_generated,
                        "rules_accepted": self._state.rules_accepted,
                        "total_rules": len(self._domain.rules),
                        "legal_doc_hash": self._state.legal_doc_hash,
                        "timestamp": datetime.now(UTC).isoformat(),
                    })
                    audit_entry_id = entry.entry_id
                except AuditWriteError as e:
                    logger.error("Audit write failed on release (non-fatal): %s", e)

            return ReleaseResult(
                success=True,
                version=version,
                exported_files=exported,
                audit_entry_id=audit_entry_id,
            )

        except Exception as e:
            logger.error("Release failed: %s", e)
            return ReleaseResult(success=False, error=str(e))


def compute_doc_hash(content: str) -> str:
    """Compute SHA-256 hash of a legal document."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
