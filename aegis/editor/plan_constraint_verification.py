"""AEGIS-2707 (Epic 27) — Plan-Constraint Verification Pipeline.

Static analysis for the plan-constraints declared in a domain. Runs
*after* IR compilation, so the input is a tuple of
``DDICPlanConstraint`` rather than the v1 ``PlanNormFrame`` or the v2
``PlanConstraintStatement`` — the verifier sees the unified IR and the
output is identical regardless of the load path.

Three stages, modeled on the existing 4-stage ``VerificationPipeline``
pattern but operating on the whole plan-constraint set rather than a
single ``RuleProposal``:

1. **symbol** — every ``action-type`` argument must be known in the
   ``ActionTypeRegistry``; per-kind argument shapes must match
   (``forbid-aggregate`` threshold integer ≥ 0, ``obligate-within``
   timeframe int ≥ 0 or one of three named symbols).

2. **conflict** — detect cycles in ``obligate-sequence`` (DFS) and
   contradictions between ``forbid-aggregate X 0`` and any norm
   that obliges agents to do ``X``.

3. **functional** — optional mini-plan execution. Skipped while the
   plan-evaluator (AEGIS-2708) is not yet wired in; the hook stays
   so 2710 can plug it in without changing the surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic_ir import (
    DDICCompound,
    DDICInteger,
    DDICPlanConstraint,
    DDICSymbol,
    PlanConstraintKind,
)
from aegis.guard.registry import ActionTypeRegistry


class PlanStageStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class PlanStageResult:
    """Result of a single plan-constraint verification stage."""

    stage: str
    status: PlanStageStatus
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
class PlanVerificationResult:
    """Aggregate result of all plan-constraint verification stages.

    The two top-level lists ``plan_constraint_cycles`` and
    ``plan_constraint_conflicts`` are the AEGIS-2707 acceptance flags;
    they remain empty when verification passes. Cycles are reported
    as the minimal cycle path (e.g. ``["A", "B", "A"]``) so a CI
    diagnostic can quote the offending chain.
    """

    passed: bool
    stages: list[PlanStageResult] = field(default_factory=list)
    plan_constraint_cycles: list[list[str]] = field(default_factory=list)
    plan_constraint_conflicts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "stages": [s.to_dict() for s in self.stages],
            "plan_constraint_cycles": list(self.plan_constraint_cycles),
            "plan_constraint_conflicts": list(self.plan_constraint_conflicts),
        }


_VALID_TIMEFRAME_SYMBOLS = frozenset(
    {"immediate", "same-session", "end-of-plan"}
)


def verify_plan_constraints(
    constraints: tuple[DDICPlanConstraint, ...],
    registry: ActionTypeRegistry | None = None,
    existing_norms: list[NormFrame] | None = None,
) -> PlanVerificationResult:
    """Run all three plan-constraint verification stages.

    Stage runs in order: symbol → conflict → functional. The pipeline
    does NOT short-circuit between stages — every stage runs even when
    an earlier stage failed, so a single CI invocation reports as
    many issues as possible. (This is the inverse of the
    ``VerificationPipeline.verify`` short-circuit policy and follows
    AEGIS-2706's deferred-validation reasoning: batch-style domain
    checks are more useful when they show every issue at once.)

    Args:
        constraints: The compiled plan-constraints from a DDICModule.
            Empty tuple is accepted and trivially passes.
        registry: Optional ``ActionTypeRegistry`` for symbol checks.
            ``None`` skips the action-type-known check (useful in
            unit tests with synthetic constraints).
        existing_norms: Optional list of NormFrames from the same
            module, used by stage 3 to detect contradictions between
            ``forbid-aggregate X 0`` and ``oughtToDo ?agent X``.

    Returns:
        ``PlanVerificationResult`` with one ``PlanStageResult`` per
        stage and the two acceptance-criteria flag lists populated.
    """
    stages: list[PlanStageResult] = []

    symbol_result = _stage_symbol(constraints, registry)
    stages.append(symbol_result)

    conflict_result, cycles, conflicts = _stage_conflict(
        constraints, existing_norms or []
    )
    stages.append(conflict_result)

    functional_result = _stage_functional()
    stages.append(functional_result)

    passed = all(
        s.status != PlanStageStatus.FAIL for s in stages
    )
    return PlanVerificationResult(
        passed=passed,
        stages=stages,
        plan_constraint_cycles=cycles,
        plan_constraint_conflicts=conflicts,
    )


# ── Stage 1: Symbol ────────────────────────────────────────────────


def _stage_symbol(
    constraints: tuple[DDICPlanConstraint, ...],
    registry: ActionTypeRegistry | None,
) -> PlanStageResult:
    """Symbol-stage: check action-types are registered + per-kind shape."""
    issues: list[str] = []

    for c in constraints:
        # Per-kind argument shape validation (deferred from AEGIS-2706
        # parser so multiple errors surface in one pass).
        shape_issue = _validate_argument_shape(c)
        if shape_issue is not None:
            issues.append(shape_issue)
            # Skip action-type symbol check when the shape is broken
            # — the action-type is still in args[0] but the rest may
            # be garbled and any follow-up diagnostic would be noise.

        # Action-type is always args[0] for the four canonical kinds.
        if registry is not None and c.args:
            action_term = c.args[0]
            if (
                isinstance(action_term, DDICSymbol)
                and not registry.is_known(action_term.value)
            ):
                issues.append(
                    f"Unknown action-type {action_term.value!r} in "
                    f"{c.kind.value} at {c.source_ref}",
                )

    if issues:
        return PlanStageResult(
            stage="symbol",
            status=PlanStageStatus.FAIL,
            message=f"{len(issues)} symbol issue(s) detected.",
            details={"issues": issues},
        )

    return PlanStageResult(
        stage="symbol",
        status=PlanStageStatus.PASS,
        message=f"All {len(constraints)} plan-constraint(s) pass symbol checks.",
    )


def _validate_argument_shape(c: DDICPlanConstraint) -> str | None:
    """Per-kind shape validation. Returns an error message or None.

    ``forbid-aggregate``: args[1] must be DDICInteger with value >= 0.
    ``obligate-within``: args[1] must be DDICInteger >= 0 OR a
    DDICSymbol whose value is one of the three named timeframes.
    ``obligate-sequence`` and ``require-precondition``: args are
    free-form at this layer and validated later (cycles for
    sequence; the precondition shape is whatever the evaluator
    supports).
    """
    if c.kind == PlanConstraintKind.FORBID_AGGREGATE:
        if len(c.args) != 2:
            return (
                f"{c.kind.value} at {c.source_ref} must have 2 arguments, "
                f"got {len(c.args)}"
            )
        threshold = c.args[1]
        if not isinstance(threshold, DDICInteger):
            return (
                f"{c.kind.value} threshold must be an integer at "
                f"{c.source_ref}, got {type(threshold).__name__}"
            )
        if threshold.value < 0:
            return (
                f"{c.kind.value} threshold must be >= 0 at "
                f"{c.source_ref}, got {threshold.value}"
            )
        return None

    if c.kind == PlanConstraintKind.OBLIGATE_WITHIN:
        if len(c.args) != 2:
            return (
                f"{c.kind.value} at {c.source_ref} must have 2 arguments, "
                f"got {len(c.args)}"
            )
        timeframe = c.args[1]
        if isinstance(timeframe, DDICInteger):
            if timeframe.value < 0:
                return (
                    f"{c.kind.value} numeric timeframe must be >= 0 at "
                    f"{c.source_ref}, got {timeframe.value}"
                )
            return None
        if isinstance(timeframe, DDICSymbol):
            if timeframe.value not in _VALID_TIMEFRAME_SYMBOLS:
                allowed = ", ".join(sorted(_VALID_TIMEFRAME_SYMBOLS))
                return (
                    f"{c.kind.value} timeframe must be integer >= 0 or one "
                    f"of [{allowed}] at {c.source_ref}, got "
                    f"{timeframe.value!r}"
                )
            return None
        return (
            f"{c.kind.value} timeframe must be integer or symbol at "
            f"{c.source_ref}, got {type(timeframe).__name__}"
        )

    if c.kind == PlanConstraintKind.REQUIRE_PRECONDITION:
        if len(c.args) != 2:
            return (
                f"{c.kind.value} at {c.source_ref} must have 2 arguments, "
                f"got {len(c.args)}"
            )
        # The precondition is expected to be a state predicate;
        # accept DDICCompound or DDICSymbol but reject naked integers.
        precond = c.args[1]
        if isinstance(precond, DDICInteger):
            return (
                f"{c.kind.value} precondition must be a predicate, got "
                f"integer at {c.source_ref}"
            )
        return None

    if c.kind == PlanConstraintKind.OBLIGATE_SEQUENCE:
        if len(c.args) != 2:
            return (
                f"{c.kind.value} at {c.source_ref} must have 2 arguments, "
                f"got {len(c.args)}"
            )
        return None

    # Future kinds: defensive — fail loudly so a new kind without
    # verifier support doesn't slip through.
    return f"Unsupported plan-constraint kind {c.kind!r} at {c.source_ref}"


# ── Stage 2: Conflict ──────────────────────────────────────────────


def _stage_conflict(
    constraints: tuple[DDICPlanConstraint, ...],
    existing_norms: list[NormFrame],
) -> tuple[PlanStageResult, list[list[str]], list[dict[str, Any]]]:
    """Detect cycles and obligation/forbid contradictions."""
    cycles = _detect_obligate_sequence_cycles(constraints)
    conflicts = _detect_aggregation_conflicts(constraints, existing_norms)

    if not cycles and not conflicts:
        return (
            PlanStageResult(
                stage="conflict",
                status=PlanStageStatus.PASS,
                message="No plan-constraint conflicts.",
            ),
            cycles,
            conflicts,
        )

    pieces: list[str] = []
    if cycles:
        pieces.append(f"{len(cycles)} cycle(s) in obligate-sequence")
    if conflicts:
        pieces.append(f"{len(conflicts)} obligation/forbid conflict(s)")

    return (
        PlanStageResult(
            stage="conflict",
            status=PlanStageStatus.FAIL,
            message="; ".join(pieces),
            details={"cycles": cycles, "conflicts": conflicts},
        ),
        cycles,
        conflicts,
    )


def _detect_obligate_sequence_cycles(
    constraints: tuple[DDICPlanConstraint, ...],
) -> list[list[str]]:
    """DFS-based cycle detection on the obligate-sequence digraph.

    Each ``obligate-sequence A B`` is a directed edge A→B. Returns a
    list of cycle paths; each cycle is reported as ``[a, b, ..., a]``
    so the duplicate at the end signals the back-edge.
    """
    graph: dict[str, list[str]] = {}
    for c in constraints:
        if c.kind != PlanConstraintKind.OBLIGATE_SEQUENCE:
            continue
        if len(c.args) != 2:
            continue
        head, tail = c.args
        if not (isinstance(head, DDICSymbol) and isinstance(tail, DDICSymbol)):
            continue
        graph.setdefault(head.value, []).append(tail.value)

    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        path.append(node)
        for neighbour in graph.get(node, []):
            n_color = color.get(neighbour, WHITE)
            if n_color == GRAY:
                # Back-edge — extract the cycle.
                start = path.index(neighbour)
                cycle = path[start:] + [neighbour]
                key = tuple(_canonical_cycle(cycle))
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(cycle)
            elif n_color == WHITE:
                dfs(neighbour, path)
        color[node] = BLACK
        path.pop()

    for node in list(graph.keys()):
        if color.get(node, WHITE) == WHITE:
            dfs(node, [])

    return cycles


def _canonical_cycle(cycle: list[str]) -> list[str]:
    """Rotate a cycle so the lexicographically smallest node is first.

    Cycles ``A→B→A`` and ``B→A→B`` describe the same loop — canonical
    form lets us de-duplicate. Drops the trailing duplicate before
    rotating, then re-appends it so the back-edge is still visible.
    """
    if len(cycle) < 2:
        return cycle
    body = cycle[:-1]  # drop trailing duplicate
    pivot = body.index(min(body))
    rotated = body[pivot:] + body[:pivot]
    return rotated + [rotated[0]]


def _detect_aggregation_conflicts(
    constraints: tuple[DDICPlanConstraint, ...],
    existing_norms: list[NormFrame],
) -> list[dict[str, Any]]:
    """Find ``forbid-aggregate X 0`` paired with any norm that
    obliges some agent to do ``X``.

    The threshold-zero case is special: it forbids the action
    altogether, which directly contradicts any obligation to do it.
    Higher thresholds (1, 2, ...) do not form an a-priori
    contradiction with a single obligation — they bound the count,
    not the existence — so they're left to the evaluator.
    """
    from aegis.deontic.modality import DeonticModality

    conflicts: list[dict[str, Any]] = []
    for c in constraints:
        if c.kind != PlanConstraintKind.FORBID_AGGREGATE:
            continue
        if len(c.args) != 2:
            continue
        action, threshold = c.args
        if not isinstance(action, DDICSymbol):
            continue
        if not isinstance(threshold, DDICInteger):
            continue
        if threshold.value != 0:
            continue
        for norm in existing_norms:
            if norm.modality != DeonticModality.OBLIGATORY:
                continue
            if not norm.proposition:
                continue
            head = norm.proposition[0]
            if str(head) == action.value:
                conflicts.append({
                    "kind": "forbid-aggregate-zero-vs-obligation",
                    "constraint_id": c.constraint_id,
                    "constraint_source": c.source_ref,
                    "action_type": action.value,
                    "obligated_by_agent": norm.agent_pattern,
                    "obligation_source": norm.source,
                })
    return conflicts


# ── Stage 3: Functional ────────────────────────────────────────────


def _stage_functional() -> PlanStageResult:
    """Stage 3 — wired in by AEGIS-2710. For now it returns SKIP.

    The plan-evaluator does not exist yet; once AEGIS-2708 lands we
    can build a tiny single-step plan from each constraint and call
    ``evaluate_plan_module`` to confirm the constraint is reachable
    and produces the expected violation pattern. AEGIS-2710 will add
    that here.
    """
    return PlanStageResult(
        stage="functional",
        status=PlanStageStatus.SKIP,
        message=(
            "Functional stage skipped — plan-evaluator (AEGIS-2708) "
            "not yet implemented."
        ),
    )


__all__ = [
    "DDICCompound",  # re-exported for tests so they don't reach into engine
    "PlanStageResult",
    "PlanStageStatus",
    "PlanVerificationResult",
    "verify_plan_constraints",
]
