"""AEGIS-1708: Host Integration Rules for Information Flow Control.

Extends the host-contract framework (HC-001 through HC-004) with
IFC-specific contracts (HC-005 through HC-008) that verify the host
application correctly integrates the retrieval broker, classifications,
and recipient constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aegis.redteam.tools import WorkspaceFileRuntime


@dataclass(frozen=True, slots=True)
class IFCHostContract:
    """Configuration for IFC host-contract checks.

    Attributes:
        contract_id: Identifier for this contract set.
        sensitive_paths: File paths known to contain classified content.
        mandatory_broker: Whether the broker must be configured.
        classification_required: Whether all workspace files must have a classification.
        recipient_constraints: Maps recipients to allowed classification levels.
    """

    contract_id: str
    sensitive_paths: tuple[str, ...] = ()
    mandatory_broker: bool = True
    classification_required: bool = True
    recipient_constraints: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IFCContractViolation:
    """A single IFC host-contract violation."""

    code: str
    severity: str
    message: str
    detail: str = ""


def check_ifc_contracts(
    contract: IFCHostContract,
    workspace_files: dict[str, WorkspaceFileRuntime],
    *,
    broker_configured: bool = False,
    tool_suite_tools: list[str] | None = None,
) -> list[IFCContractViolation]:
    """Run IFC host-contract checks.

    Contracts:
    - HC-005: Broker must be configured when mandatory_broker is True.
    - HC-006: No raw classified reads without broker (checks tool suite).
    - HC-007: All workspace files must have a classification label.
    - HC-008: Recipient constraints must be covered by MELD norms
              (advisory — checks that constraints are declared).
    """
    violations: list[IFCContractViolation] = []

    # HC-005: Broker configured
    if contract.mandatory_broker and not broker_configured:
        violations.append(IFCContractViolation(
            code="HC-005",
            severity="critical",
            message="RetrievalBroker is not configured but is mandatory.",
            detail=(
                "The IFC host contract requires a RetrievalBroker to be "
                "wired into the tool suite. Without it, classified content "
                "reaches the LLM unfiltered."
            ),
        ))

    # HC-006: No raw classified tools without broker
    if not broker_configured:
        raw_read_tools = {"read_workspace_file", "search_workspace_files"}
        if tool_suite_tools:
            has_raw_reads = bool(raw_read_tools & set(tool_suite_tools))
        else:
            has_raw_reads = True  # Assume worst case

        classified_files = [
            path for path, entry in workspace_files.items()
            if entry.classification.lower() not in ("public", "")
        ]
        if has_raw_reads and classified_files:
            violations.append(IFCContractViolation(
                code="HC-006",
                severity="critical",
                message=(
                    f"Classified files ({len(classified_files)}) are accessible "
                    "via raw read/search tools without broker filtering."
                ),
                detail=", ".join(sorted(classified_files)[:5]),
            ))

    # HC-007: All workspace files must have classification
    if contract.classification_required:
        unclassified = [
            path for path, entry in workspace_files.items()
            if not entry.classification or entry.classification.strip() == ""
        ]
        if unclassified:
            violations.append(IFCContractViolation(
                code="HC-007",
                severity="high",
                message=(
                    f"{len(unclassified)} workspace file(s) have no "
                    "classification label."
                ),
                detail=", ".join(sorted(unclassified)[:5]),
            ))

    # HC-008: Recipient constraints declared
    if contract.recipient_constraints:
        for recipient, allowed_levels in contract.recipient_constraints.items():
            if not allowed_levels:
                violations.append(IFCContractViolation(
                    code="HC-008",
                    severity="medium",
                    message=(
                        f"Recipient {recipient!r} has empty allowed-classification "
                        "list — no MELD norms can cover this constraint."
                    ),
                ))

    # HC-009: Channel registry coverage (AEGIS-1808)
    # Every channel must have at least one verifying scenario
    from aegis.ifc.channel_registry import uncovered_channels
    gaps = uncovered_channels()
    if gaps:
        channel_ids = ", ".join(ch.channel_id for ch in gaps)
        violations.append(IFCContractViolation(
            code="HC-009",
            severity="critical",
            message=(
                f"{len(gaps)} information flow channel(s) have no verifying "
                f"red-team scenario: {channel_ids}"
            ),
            detail=channel_ids,
        ))

    # HC-010: Per-channel mandatory mediation (AEGIS-1805)
    # Every channel declared as requires_broker / requires_guard must
    # have a Channel-to-Action mapping. Without the mapping the channel
    # cannot be guarded — an architectural gap, not a runtime warning.
    from aegis.ifc.channel_action_mapping import unmapped_channels as _unmapped_action
    from aegis.ifc.channel_registry import channels_requiring_broker, channels_requiring_guard
    mapped_unguarded = _unmapped_action()
    if mapped_unguarded:
        ids = ", ".join(ch.channel_id for ch in mapped_unguarded)
        violations.append(IFCContractViolation(
            code="HC-010",
            severity="critical",
            message=(
                f"{len(mapped_unguarded)} information flow channel(s) have no "
                f"Channel-to-Action mapping: {ids}. Without a mapping the "
                "channel is unguardable."
            ),
            detail=ids,
        ))

    # HC-011: Broker-required channels must have BROKER mediation_type.
    # Catches misconfiguration where a channel is declared
    # requires_broker=True but its mapping uses a different mediation
    # mechanism, which would let an audit pass while the runtime
    # bypasses the broker.
    from aegis.ifc.channel_action_mapping import mapping_by_channel_id
    from aegis.ifc.channel_registry import MediationType
    for ch in channels_requiring_broker():
        mapping = mapping_by_channel_id(ch.channel_id)
        if mapping is None:
            # Already caught by HC-010.
            continue
        if ch.mediation_type != MediationType.BROKER:
            violations.append(IFCContractViolation(
                code="HC-011",
                severity="critical",
                message=(
                    f"Channel {ch.channel_id!r} declares requires_broker=True "
                    f"but mediation_type is {ch.mediation_type.value}, not BROKER."
                ),
                detail=ch.channel_id,
            ))

    # HC-012: Guard-required channels must opt in to guard interposition
    # somehow. This catches the "channel says it needs Guard but the
    # registry entry has guard_interposition=False" mismatch.
    for ch in channels_requiring_guard():
        if not ch.guard_interposition:
            violations.append(IFCContractViolation(
                code="HC-012",
                severity="critical",
                message=(
                    f"Channel {ch.channel_id!r} requires the Guard but "
                    "guard_interposition=False in the registry — the "
                    "Guard cannot sit between source and sink."
                ),
                detail=ch.channel_id,
            ))

    return violations


# ── Release-Gate evaluation (AEGIS-1805) ───────────────────────────


@dataclass(frozen=True, slots=True)
class ReleaseGateResult:
    """Aggregated severity counts + binary release-block decision.

    Attributes:
        violations: the input list, surfaced unchanged for logging.
        critical_count / high_count / medium_count: severity counts.
        release_blocked: True iff at least one ``critical`` violation
            exists. Maps directly to a non-zero exit code in CI gates.
    """

    violations: tuple[IFCContractViolation, ...]
    critical_count: int
    high_count: int
    medium_count: int
    release_blocked: bool

    def exit_code(self) -> int:
        """0 when release is unblocked; 1 when blocked. Used by the
        CI gate to translate the result into a process exit status."""
        return 1 if self.release_blocked else 0

    def summary(self) -> str:
        """Human-readable one-line summary for CI logs."""
        if self.release_blocked:
            return (
                f"RELEASE BLOCKED: {self.critical_count} critical, "
                f"{self.high_count} high, {self.medium_count} medium"
            )
        return (
            f"Release-gate OK: 0 critical, {self.high_count} high, "
            f"{self.medium_count} medium"
        )


def evaluate_release_gate(
    violations: list[IFCContractViolation],
) -> ReleaseGateResult:
    """Aggregate violations into a release-gate decision.

    Per AEGIS-1805 acceptance: any ``critical`` violation blocks the
    release. ``high`` and ``medium`` are reported but do not block —
    the reasoning is that high-severity issues that aren't critical
    are typically operational warnings (e.g. classification gaps that
    can be fixed without touching the Guard).
    """
    critical = sum(1 for v in violations if v.severity == "critical")
    high = sum(1 for v in violations if v.severity == "high")
    medium = sum(1 for v in violations if v.severity == "medium")
    return ReleaseGateResult(
        violations=tuple(violations),
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        release_blocked=critical > 0,
    )
