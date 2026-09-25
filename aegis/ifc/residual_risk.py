"""Residual Risk Register (AEGIS-2004, Epic 20).

Explicit, machine-readable register of risks that AEGIS does NOT
mitigate. An honest 100%-Guard claim requires documented exclusions —
the alternative is implicit overclaiming.

Each entry has a stable ID, a free-form rationale, an affected
subsystem/channel, a current status (``open``, ``accepted``,
``mitigated``), and a compensating control description.

The register is consumed by the 100%-Guard-Claim gate (AEGIS-2003)
which requires that *every* residual risk is documented before the
``full_guard_coverage`` claim can be carried — even if the entries
are ``open``. The requirement is transparency, not resolution.

Initial entries (RR-001..005) reflect the architectural exclusions
documented in ``docs/assessment/GUARANTEE_BOUNDARY.md`` — paraphrastic
disclosure, LLM self-attestation, lateral channels, multi-agent
handoff, and norm-versioning during running sessions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

RiskStatus = Literal["open", "accepted", "mitigated"]


@dataclass(frozen=True, slots=True)
class ResidualRisk:
    """One entry in the residual-risk register."""

    risk_id: str
    """Stable identifier, e.g. ``"RR-001"``."""

    affected_subsystem: str
    """Channel ID or subsystem name."""

    rationale: str
    """Why this risk exists / why it's not closed."""

    status: RiskStatus = "open"

    compensating_control: str = ""
    """Description of any compensating measure (operational
    procedure, monitoring, process). Empty when no compensation
    exists."""


@dataclass(frozen=True, slots=True)
class ResidualRiskRegister:
    """Machine-readable register of residual risks."""

    risks: tuple[ResidualRisk, ...] = ()

    def by_id(self, risk_id: str) -> ResidualRisk | None:
        for r in self.risks:
            if r.risk_id == risk_id:
                return r
        return None

    def by_status(self, status: RiskStatus) -> tuple[ResidualRisk, ...]:
        return tuple(r for r in self.risks if r.status == status)

    def to_dict(self) -> dict:
        return {
            "risks": [
                {
                    "risk_id": r.risk_id,
                    "affected_subsystem": r.affected_subsystem,
                    "rationale": r.rationale,
                    "status": r.status,
                    "compensating_control": r.compensating_control,
                }
                for r in self.risks
            ],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ── Initial entries from GUARANTEE_BOUNDARY.md ───────────────────

DEFAULT_REGISTER = ResidualRiskRegister(
    risks=(
        ResidualRisk(
            risk_id="RR-001",
            affected_subsystem="output_filter",
            rationale=(
                "Paraphrastic disclosure (semantically-equivalent "
                "rewordings of classified content) cannot be detected "
                "by the pattern-based OutputFilter. The Guard's I5 "
                "guarantee covers identical-string disclosure only."
            ),
            status="accepted",
            compensating_control=(
                "OutputFilter is defense-in-depth; the formal "
                "disclosure layer (Epic 19) operates on the action "
                "side, where intent is explicit."
            ),
        ),
        ResidualRisk(
            risk_id="RR-002",
            affected_subsystem="action_proposition",
            rationale=(
                "LLM self-attestation of recipient/purpose fields in "
                "the action proposition is not externally verified. A "
                "compromised LLM may declare a benign recipient while "
                "actually disclosing to an external sink."
            ),
            status="accepted",
            compensating_control=(
                "Tool-Argument Mediation (AEGIS-1804) catches "
                "tainted-string leaks. Recipient verification is the "
                "host integration's responsibility."
            ),
        ),
        ResidualRisk(
            risk_id="RR-003",
            affected_subsystem="lateral_channels",
            rationale=(
                "File-write side effects, environment variables, and "
                "process-side channels are outside the action-check "
                "perimeter. AEGIS evaluates *named* actions only."
            ),
            status="open",
            compensating_control=(
                "Host integrations restrict the tool surface so "
                "lateral channels are not reachable from the LLM "
                "without an aegis_check call."
            ),
        ),
        ResidualRisk(
            risk_id="RR-004",
            affected_subsystem="multi_agent_handoff",
            rationale=(
                "Multi-agent conversations where one AEGIS-mediated "
                "agent hands off to another are not currently mediated "
                "as a unit. Each agent runs its own session-scope "
                "Guard."
            ),
            status="open",
            compensating_control=(
                "Per-agent audit trails make handoffs reconstructible "
                "post-hoc; cross-agent norm-flow is research scope."
            ),
        ),
        ResidualRisk(
            risk_id="RR-005",
            affected_subsystem="domain_reload",
            rationale=(
                "Reloading the domain rule-set in a running session "
                "could change the verdict for in-flight requests. "
                "The atomic-snapshot semantics (D-005, D-006) bound "
                "this to per-request determinism but not session-"
                "level monotonicity."
            ),
            status="accepted",
            compensating_control=(
                "Audit trail records the domain version per verdict; "
                "operational policy disallows reloads during active "
                "sessions."
            ),
        ),
    ),
)
