"""AEGIS-1403: Verification Pipeline.

4-stage verification for every LLM-generated rule:
1. Syntax  — parse_meld() must succeed
2. Symbol  — extract_norm() + known-symbol check + typo suggestions
3. Conflict — NormFrame.conflicts_with() against all existing norms
4. Functional — build temporary Guard, run test action, verify verdict

Short-circuits on first FAIL — no conflict check on syntactically invalid MELD.
Each stage returns detailed diagnostics, not just pass/fail.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.editor.domain_model import DomainInfo, RuleInfo
from aegis.editor.meld_generator import RuleProposal
from aegis.editor.meld_writer import export_domain
from aegis.errors import MeldSyntaxError
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision
from aegis.kb.meld_loader import _KNOWN_PREDICATES, extract_norm, parse_meld

logger = logging.getLogger(__name__)


class StageStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class StageResult:
    """Result of a single verification stage."""

    stage: str
    status: StageStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class VerificationResult:
    """Result of the complete 4-stage verification pipeline."""

    passed: bool
    stages: list[StageResult] = field(default_factory=list)
    norm: NormFrame | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "passed": self.passed,
            "stages": [s.to_dict() for s in self.stages],
        }
        if self.norm is not None:
            result["norm"] = {
                "code": self.norm.code,
                "agent": self.norm.agent_pattern,
                "modality": self.norm.modality.value,
                "proposition": str(self.norm.proposition),
            }
        return result


class VerificationPipeline:
    """4-stage verification pipeline for LLM-generated rules.

    Usage::

        pipeline = VerificationPipeline(domain)
        result = pipeline.verify(proposal)
        if result.passed:
            # Rule is safe to add
            ...
    """

    def __init__(self, domain: DomainInfo) -> None:
        self._domain = domain
        self._existing_norms = self._build_existing_norms()

    def verify(self, proposal: RuleProposal) -> VerificationResult:
        """Run all 4 verification stages. Short-circuits on first FAIL."""
        stages: list[StageResult] = []

        # Stage 1: Syntax
        syntax_result, assertions = self._stage_syntax(proposal.meld_expression)
        stages.append(syntax_result)
        if syntax_result.status == StageStatus.FAIL:
            stages.extend(self._skip_remaining(["symbol", "conflict", "functional"]))
            return VerificationResult(passed=False, stages=stages)

        # Stage 2: Symbol
        symbol_result, norm = self._stage_symbol(assertions)
        stages.append(symbol_result)
        if symbol_result.status == StageStatus.FAIL:
            stages.extend(self._skip_remaining(["conflict", "functional"]))
            return VerificationResult(passed=False, stages=stages)

        # Stage 3: Conflict
        conflict_result = self._stage_conflict(norm)
        stages.append(conflict_result)
        if conflict_result.status == StageStatus.FAIL:
            stages.extend(self._skip_remaining(["functional"]))
            return VerificationResult(passed=False, stages=stages, norm=norm)

        # Stage 4: Functional
        functional_result = self._stage_functional(proposal, norm)
        stages.append(functional_result)

        passed = all(s.status == StageStatus.PASS for s in stages)
        return VerificationResult(passed=passed, stages=stages, norm=norm)

    # ── Stage 1: Syntax ───────────────────────────────────────────

    def _stage_syntax(
        self, meld_expression: str,
    ) -> tuple[StageResult, list[tuple[Any, ...]]]:
        """Parse the MELD expression. Returns (result, assertions)."""
        try:
            assertions = parse_meld(meld_expression, file="<generated>")
            if not assertions:
                return (
                    StageResult(
                        stage="syntax",
                        status=StageStatus.FAIL,
                        message="Empty MELD expression — no assertions found.",
                    ),
                    [],
                )
            return (
                StageResult(
                    stage="syntax",
                    status=StageStatus.PASS,
                    message=f"Parsed {len(assertions)} assertion(s).",
                    details={"assertion_count": len(assertions)},
                ),
                assertions,
            )
        except MeldSyntaxError as e:
            return (
                StageResult(
                    stage="syntax",
                    status=StageStatus.FAIL,
                    message=f"Syntax error: {e}",
                    details={"file": e.file, "line": e.line},
                ),
                [],
            )

    # ── Stage 2: Symbol ───────────────────────────────────────────

    def _stage_symbol(
        self, assertions: list[tuple[Any, ...]],
    ) -> tuple[StageResult, NormFrame | None]:
        """Validate predicate arity and check known symbols."""
        issues: list[str] = []
        suggestions: dict[str, list[str]] = {}
        norm: NormFrame | None = None

        for assertion in assertions:
            predicate = assertion[0] if assertion else None
            if not isinstance(predicate, str):
                issues.append(f"Non-string predicate: {predicate!r}")
                continue

            # Check known predicate
            if predicate not in _KNOWN_PREDICATES:
                close = _find_close_matches(predicate, _KNOWN_PREDICATES)
                msg = f"Unknown predicate: {predicate!r}"
                if close:
                    msg += f" — did you mean: {', '.join(close)}?"
                    suggestions[predicate] = close
                issues.append(msg)
                continue

            # Extract norm (validates arity)
            try:
                extracted = extract_norm(assertion, "<generated>", "<generated>")
                if extracted is not None:
                    norm = extracted
            except MeldSyntaxError as e:
                issues.append(f"Arity error: {e}")
                continue

        # Check agent role is known in domain
        if norm is not None and norm.agent_pattern != "*":
            known_roles = {r.name for r in self._domain.roles}
            if known_roles and norm.agent_pattern not in known_roles:
                close = _find_close_matches(norm.agent_pattern, known_roles)
                msg = f"Unknown agent role: {norm.agent_pattern!r}"
                if close:
                    msg += f" — did you mean: {', '.join(close)}?"
                    suggestions[norm.agent_pattern] = close
                issues.append(msg)

        # Check code is known in domain
        if norm is not None and norm.code:
            known_codes = {c.name for c in self._domain.codes}
            if known_codes and norm.code not in known_codes:
                close = _find_close_matches(norm.code, known_codes)
                msg = f"Unknown code of conduct: {norm.code!r}"
                if close:
                    msg += f" — did you mean: {', '.join(close)}?"
                    suggestions[norm.code] = close
                issues.append(msg)

        if issues:
            return (
                StageResult(
                    stage="symbol",
                    status=StageStatus.FAIL,
                    message="; ".join(issues),
                    details={"issues": issues, "suggestions": suggestions},
                ),
                norm,
            )

        return (
            StageResult(
                stage="symbol",
                status=StageStatus.PASS,
                message="All symbols valid.",
                details={"suggestions": suggestions} if suggestions else {},
            ),
            norm,
        )

    # ── Stage 3: Conflict ─────────────────────────────────────────

    def _stage_conflict(self, norm: NormFrame | None) -> StageResult:
        """Check for unresolved conflicts with existing norms."""
        if norm is None:
            return StageResult(
                stage="conflict",
                status=StageStatus.PASS,
                message="No norm to check (non-deontic assertion).",
            )

        conflicts: list[dict[str, str]] = []
        for existing in self._existing_norms:
            if norm.conflicts_with(existing):
                # Check if resolved by specificity or prevalence
                resolved = (
                    norm.specificity != existing.specificity
                    or norm.code != existing.code
                )
                if not resolved:
                    conflicts.append({
                        "existing_code": existing.code,
                        "existing_agent": existing.agent_pattern,
                        "existing_modality": existing.modality.value,
                        "existing_proposition": str(existing.proposition),
                        "resolution": "Unresolved",
                    })

        if conflicts:
            return StageResult(
                stage="conflict",
                status=StageStatus.FAIL,
                message=f"{len(conflicts)} unresolved conflict(s) detected.",
                details={"conflicts": conflicts},
            )

        return StageResult(
            stage="conflict",
            status=StageStatus.PASS,
            message="No unresolved conflicts.",
        )

    # ── Stage 4: Functional ───────────────────────────────────────

    def _stage_functional(
        self, proposal: RuleProposal, norm: NormFrame | None,
    ) -> StageResult:
        """Build a temporary Guard with the new rule and run a test action."""
        if norm is None:
            return StageResult(
                stage="functional",
                status=StageStatus.PASS,
                message="No norm to functionally test.",
            )

        try:
            # Build a temporary domain with the new rule added
            temp_domain = DomainInfo(
                id=self._domain.id,
                name=self._domain.name,
                roles=list(self._domain.roles),
                codes=list(self._domain.codes),
                rules=list(self._domain.rules),
            )
            new_rule = RuleInfo(
                id="test-new",
                code=proposal.code_of_conduct,
                agent_role=proposal.agent_role,
                modality=proposal.modality,
                proposition=proposal.action_type,
                defeasible=proposal.defeasible,
            )
            temp_domain.rules.append(new_rule)

            # Export to temp directory and build Guard
            with tempfile.TemporaryDirectory() as tmpdir:
                paths = export_domain(temp_domain, Path(tmpdir))
                guard = Guard.from_meld_files(paths)

                # Build test action
                test_action = Action(
                    action_type=proposal.action_type,
                    agent_id=proposal.agent_role,
                    proposition={
                        k: v for k, v in proposal.proposition_parameters.items()
                    },
                )

                verdict = guard.check(test_action)

                # Determine expected verdict
                expected = {
                    "OBLIGATORY": Decision.PERMITTED,  # obligatory implies permitted
                    "FORBIDDEN": Decision.FORBIDDEN,
                    "PERMITTED": Decision.PERMITTED,
                }.get(proposal.modality, Decision.PERMITTED)

                if verdict.decision == expected:
                    return StageResult(
                        stage="functional",
                        status=StageStatus.PASS,
                        message=f"Guard returned {verdict.decision.value} as expected.",
                        details={
                            "verdict": verdict.decision.value,
                            "expected": expected.value,
                            "justification": list(verdict.justification_chain),
                        },
                    )
                else:
                    return StageResult(
                        stage="functional",
                        status=StageStatus.FAIL,
                        message=(
                            f"Guard returned {verdict.decision.value}, "
                            f"expected {expected.value}."
                        ),
                        details={
                            "verdict": verdict.decision.value,
                            "expected": expected.value,
                            "justification": list(verdict.justification_chain),
                        },
                    )

        except Exception as e:
            return StageResult(
                stage="functional",
                status=StageStatus.FAIL,
                message=f"Functional test error: {e}",
                details={"error": str(e)},
            )

    # ── Helpers ────────────────────────────────────────────────────

    def _build_existing_norms(self) -> list[NormFrame]:
        """Convert domain RuleInfo back to NormFrames for conflict checking."""
        norms: list[NormFrame] = []
        for rule in self._domain.rules:
            try:
                modality = DeonticModality[rule.modality]
            except KeyError:
                continue
            prop_parts = tuple(rule.proposition.split()) if rule.proposition else ()
            norms.append(NormFrame(
                code=rule.code,
                agent_pattern=rule.agent_role,
                modality=modality,
                proposition=prop_parts,
                specificity=rule.specificity,
                defeasible=rule.defeasible,
                source=rule.source,
            ))
        return norms

    @staticmethod
    def _skip_remaining(stage_names: list[str]) -> list[StageResult]:
        return [
            StageResult(
                stage=name,
                status=StageStatus.SKIP,
                message="Skipped (prior stage failed).",
            )
            for name in stage_names
        ]


# ── Levenshtein distance for typo suggestions ────────────────────


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def _find_close_matches(
    target: str,
    candidates: set[str] | frozenset[str],
    *,
    max_distance: int = 3,
    max_results: int = 3,
) -> list[str]:
    """Find candidates within Levenshtein distance of target."""
    scored = [
        (c, _levenshtein(target.lower(), c.lower()))
        for c in candidates
    ]
    close = sorted(
        [(c, d) for c, d in scored if d <= max_distance],
        key=lambda x: x[1],
    )
    return [c for c, _ in close[:max_results]]
