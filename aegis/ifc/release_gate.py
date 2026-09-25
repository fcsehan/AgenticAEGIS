"""100%-Guard-Claim Release-Gate (AEGIS-2003, Epic 20).

Combines the Coverage Report (AEGIS-2001 + 2002), the Host-Contract
violations (AEGIS-1805), and the Bypass-count from the red-team
proof (AEGIS-2003) into a single binary decision: is the build
eligible to carry the ``full_guard_coverage`` claim, or does it
fall back to ``partial_guard_coverage``?

Per AEGIS-2003 acceptance the gate requires:

- Channel Coverage = 100% (no unregistered or unmapped sensitive
  channel)
- No open critical contract violations (HC-005..012)
- No open critical red-team findings — bypass count = 0
- Disclosure Coverage ≥ threshold (today: all disclosure channels
  declare a mediation; Epic 19 raises the bar)
- All residual risks documented in the register (AEGIS-2004)

The gate is *deterministic* and *machine-readable*: the result
serialises to JSON for CI integration and renders as Markdown for
human review.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from aegis.ifc.guard_coverage import GuardCoverageReport
from aegis.ifc.host_contract import IFCContractViolation
from aegis.ifc.residual_risk import ResidualRiskRegister


class GuardClaim(Enum):
    """The two possible release claims."""

    FULL = "full_guard_coverage"
    """Build is eligible for the 100%-Guard claim."""

    PARTIAL = "partial_guard_coverage"
    """Build falls back to the partial claim. Documentation must
    surface the gaps; the certificate must NOT carry the full claim."""


@dataclass(frozen=True, slots=True)
class GateGap:
    """One concrete reason the gate falls back to PARTIAL."""

    category: str
    """Either "coverage", "contracts", "bypass", or "residual_risk"."""

    detail: str


@dataclass(frozen=True, slots=True)
class ReleaseClaimResult:
    """Output of the 100%-Guard-Claim gate."""

    claim: GuardClaim
    coverage: GuardCoverageReport
    bypass_count: int
    critical_contract_violations: int
    open_residual_risks: int
    gaps: tuple[GateGap, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return self.claim == GuardClaim.FULL

    def to_dict(self) -> dict:
        return {
            "claim": self.claim.value,
            "passed": self.passed,
            "coverage": self.coverage.to_dict(),
            "bypass_count": self.bypass_count,
            "critical_contract_violations": self.critical_contract_violations,
            "open_residual_risks": self.open_residual_risks,
            "gaps": [
                {"category": g.category, "detail": g.detail} for g in self.gaps
            ],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        if self.passed:
            return (
                "RELEASE CLAIM: full_guard_coverage. "
                f"bypass_count=0, all coverage dimensions at 100%, "
                f"{self.open_residual_risks} residual risk(s) documented."
            )
        gap_summary = "; ".join(f"{g.category}:{g.detail}" for g in self.gaps)
        return (
            f"RELEASE CLAIM: partial_guard_coverage. Gaps: {gap_summary}"
        )


def evaluate_claim(
    coverage: GuardCoverageReport,
    contract_violations: list[IFCContractViolation],
    *,
    bypass_count: int,
    residual_register: ResidualRiskRegister | None = None,
) -> ReleaseClaimResult:
    """Evaluate the 100%-Guard claim gate.

    All four conditions must pass for ``GuardClaim.FULL``:

    1. ``coverage.all_full_coverage is True``
    2. ``bypass_count == 0``
    3. No ``critical`` contract violations
    4. All residual risks are documented (register exists, even if
       its entries are ``open`` or ``accepted`` — the requirement
       is *transparency*, not *resolution*).

    The gate produces an ordered ``gaps`` tuple so a CI report can
    print the failures in priority order.
    """
    gaps: list[GateGap] = []

    if not coverage.all_full_coverage:
        for d in coverage.all_dimensions():
            if d.uncovered_channel_ids:
                gaps.append(
                    GateGap(
                        category="coverage",
                        detail=f"{d.name} {d.percent}%: "
                        f"{', '.join(d.uncovered_channel_ids)}",
                    ),
                )

    critical_violations = [
        v for v in contract_violations if v.severity == "critical"
    ]
    if critical_violations:
        gaps.append(
            GateGap(
                category="contracts",
                detail=", ".join(v.code for v in critical_violations),
            ),
        )

    if bypass_count > 0:
        gaps.append(
            GateGap(
                category="bypass",
                detail=f"{bypass_count} bypass finding(s) — must be 0",
            ),
        )

    open_risks = 0
    if residual_register is None:
        gaps.append(
            GateGap(
                category="residual_risk",
                detail="No ResidualRiskRegister supplied; cannot certify.",
            ),
        )
    else:
        open_risks = len([
            r for r in residual_register.risks if r.status == "open"
        ])

    claim = GuardClaim.FULL if not gaps else GuardClaim.PARTIAL
    return ReleaseClaimResult(
        claim=claim,
        coverage=coverage,
        bypass_count=bypass_count,
        critical_contract_violations=len(critical_violations),
        open_residual_risks=open_risks,
        gaps=tuple(gaps),
    )
