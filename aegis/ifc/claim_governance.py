"""Claim Governance & Release Gate (AEGIS-2312, Epic 23).

Sober-binding for the strongest claims AEGIS makes in marketing and
documentation. A build is allowed to carry the claim
``"Olson DDIC implemented"`` only if the formal conformance suite
under ``tests/formal/`` is green AND the four-tier verification chain
documented in ``docs/spec/DDIC_VERIFICATION.md`` is intact.

The two strongest claims are:

1. ``OLSON_DDIC_IMPLEMENTED`` — Olson's DDIC algorithm runs end-to-end
   with the formal conformance suite green (Karli examples, Table 6.5,
   216-combination matrix, TLA+ model).
2. ``FULL_GUARD_COVERAGE`` — the 100%-Guard claim from
   ``aegis/ifc/release_gate.evaluate_claim``.

Both are gated. A build that carries ``OLSON_DDIC_IMPLEMENTED`` while
the conformance suite has failures is overclaiming; the gate makes
the inconsistency loud at release time rather than at audit time.

The implementation is **deterministic**: the gate inspects the
file-system artefacts it expects (test files, TLA+ model, docs) and
the result of running the formal suite. It does NOT call the LLM,
does NOT run the suite itself (the CI runner does that and feeds the
result in), and does NOT make probabilistic judgments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# The formal-test files that together constitute Olson conformance per
# the four-tier chain documented in docs/spec/DDIC_VERIFICATION.md.
_REQUIRED_OLSON_TESTS: tuple[str, ...] = (
    "tests/formal/test_olson_karli_examples.py",
    "tests/formal/test_olson_table_65.py",
    "tests/formal/test_olson_conformance.py",
    "tests/formal/test_ddic_soundness.py",
    "tests/formal/test_ddic_combinatorial.py",
)

_REQUIRED_DOCS: tuple[str, ...] = (
    "docs/spec/DDIC_VERIFICATION.md",
    "docs/spec/OLSON_CH6_CONFORMANCE.md",
    "docs/assessment/GUARANTEE_BOUNDARY.md",
)

_REQUIRED_FORMAL_MODELS: tuple[str, ...] = (
    "spec/formal/ddic_algorithm.tla",
    "spec/formal/narrowest_action.tla",
)


class ClaimName(Enum):
    """Strong product/research claims the release gate governs."""

    OLSON_DDIC_IMPLEMENTED = "OLSON_DDIC_IMPLEMENTED"
    """Build is eligible to claim Olson's DDIC algorithm is
    implemented and conformant."""

    FULL_GUARD_COVERAGE = "FULL_GUARD_COVERAGE"
    """Build is eligible to carry the 100%-Guard claim from
    ``release_gate.evaluate_claim``."""


@dataclass(frozen=True, slots=True)
class ClaimGap:
    """One concrete reason a claim is not eligible."""

    artefact: str
    """File path or test ID that's missing/failing."""

    reason: str


@dataclass(frozen=True, slots=True)
class ClaimEligibility:
    """Result of a claim-governance check."""

    claim: ClaimName
    eligible: bool
    gaps: tuple[ClaimGap, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "claim": self.claim.value,
            "eligible": self.eligible,
            "gaps": [
                {"artefact": g.artefact, "reason": g.reason} for g in self.gaps
            ],
        }

    def summary(self) -> str:
        if self.eligible:
            return f"CLAIM ELIGIBLE: {self.claim.value}"
        gap_summary = "; ".join(f"{g.artefact}:{g.reason}" for g in self.gaps)
        return (
            f"CLAIM BLOCKED: {self.claim.value} — gaps: {gap_summary}"
        )


def evaluate_olson_claim(
    *,
    repo_root: Path,
    formal_tests_passed: int,
    formal_tests_failed: int,
    expected_minimum_tests: int = 360,
) -> ClaimEligibility:
    """Evaluate eligibility for the ``OLSON_DDIC_IMPLEMENTED`` claim.

    All conditions must hold:

    1. Every file in ``_REQUIRED_OLSON_TESTS`` exists.
    2. Every file in ``_REQUIRED_DOCS`` exists.
    3. Every file in ``_REQUIRED_FORMAL_MODELS`` exists.
    4. ``formal_tests_failed == 0``.
    5. ``formal_tests_passed >= expected_minimum_tests``.

    The CI runner is responsible for running the formal suite and
    feeding the counts in. This function makes the gate
    deterministic-from-artefacts; it does not run pytest itself.
    """
    gaps: list[ClaimGap] = []

    for rel in _REQUIRED_OLSON_TESTS:
        if not (repo_root / rel).is_file():
            gaps.append(
                ClaimGap(artefact=rel, reason="missing formal test file"),
            )

    for rel in _REQUIRED_DOCS:
        if not (repo_root / rel).is_file():
            gaps.append(
                ClaimGap(artefact=rel, reason="missing conformance doc"),
            )

    for rel in _REQUIRED_FORMAL_MODELS:
        if not (repo_root / rel).is_file():
            gaps.append(
                ClaimGap(artefact=rel, reason="missing TLA+ model"),
            )

    if formal_tests_failed > 0:
        gaps.append(
            ClaimGap(
                artefact="tests/formal/",
                reason=(
                    f"{formal_tests_failed} formal test failure(s) — must be 0 "
                    "for Olson conformance"
                ),
            ),
        )

    if formal_tests_passed < expected_minimum_tests:
        gaps.append(
            ClaimGap(
                artefact="tests/formal/",
                reason=(
                    f"{formal_tests_passed} formal tests passed, expected at "
                    f"least {expected_minimum_tests} per the four-tier chain"
                ),
            ),
        )

    return ClaimEligibility(
        claim=ClaimName.OLSON_DDIC_IMPLEMENTED,
        eligible=not gaps,
        gaps=tuple(gaps),
    )


def evaluate_full_guard_coverage_claim(
    release_claim_passed: bool,
    *,
    bypass_count: int,
) -> ClaimEligibility:
    """Wrap the ``release_gate.evaluate_claim`` decision into the
    claim-governance vocabulary.

    A separate function — even though it just lifts the boolean — so
    the governance layer has a single seam for both claims.
    """
    gaps: list[ClaimGap] = []
    if not release_claim_passed:
        gaps.append(
            ClaimGap(
                artefact="release_gate",
                reason="release_gate.evaluate_claim did not produce FULL",
            ),
        )
    if bypass_count > 0:
        gaps.append(
            ClaimGap(
                artefact="bypass_proof",
                reason=f"{bypass_count} bypass finding(s) — must be 0",
            ),
        )
    return ClaimEligibility(
        claim=ClaimName.FULL_GUARD_COVERAGE,
        eligible=not gaps,
        gaps=tuple(gaps),
    )
