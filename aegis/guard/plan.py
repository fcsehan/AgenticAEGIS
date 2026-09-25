"""Plan / PlanStep / StateSnapshot data model (AEGIS-2701, Epic 27).

Plan-Level Governance is the third evaluation surface alongside
``Action`` (Guard.check) and disclosure-actions (Epic 19). A Plan is
an ordered sequence of declared steps; the Guard evaluates the whole
plan rather than each step in isolation, so plan-level constraints
(sequence, aggregate, timing, precondition) become expressible.

Per AEGIS-2701 the plan IR is a small set of frozen dataclasses with
a clear ``Plan.from_action(a)`` factory so the existing ``Guard.check``
contract is preserved by construction: a single-action call is the
same as a one-step plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aegis.guard.action import Action

# D-007-style limits (analogous to Action.validate_limits).
MAX_PLAN_STEPS = 500
MAX_STATE_FIELDS = 200
MAX_PLAN_SIZE_BYTES = 512_000


class ViolationType(Enum):
    """Reasons a plan can violate a plan-level constraint.

    Eight variants per AEGIS-2701 acceptance — one per concrete
    failure mode the evaluator emits.
    """

    SEQUENCE_VIOLATION = "SEQUENCE_VIOLATION"
    """An obligated step ordering was not respected."""

    AGGREGATE_VIOLATION = "AGGREGATE_VIOLATION"
    """A forbidden-aggregate constraint was triggered (e.g. count
    of permitted X exceeded threshold)."""

    TIMING_VIOLATION = "TIMING_VIOLATION"
    """An obligate-within constraint was missed."""

    PRECONDITION_VIOLATION = "PRECONDITION_VIOLATION"
    """A require-precondition constraint did not hold at the step."""

    STEP_FORBIDDEN = "STEP_FORBIDDEN"
    """A single step received FORBIDDEN under per-step delegation."""

    STEP_UNDECIDABLE = "STEP_UNDECIDABLE"
    """A single step received UNDECIDABLE."""

    OBLIGATION_UNCOVERED = "OBLIGATION_UNCOVERED"
    """A declared obligation was not satisfied by any step
    (only when ``DDICModule.require_obligation_coverage`` is True)."""

    EMPTY_PLAN = "EMPTY_PLAN"
    """The plan has zero steps; semantically blocked at evaluator
    entry rather than carried through downstream stages."""


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    """A snapshot of caller-supplied state at one point in plan
    execution.

    The Guard does NOT verify the snapshot's truthfulness — that is
    documented as I3 boundary in the guarantee boundary. The caller is
    responsible for honesty; the Guard is responsible for evaluating
    the plan against the declared snapshot.
    """

    fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Make the dict effectively read-only after construction.
        # Frozen dataclasses still allow dict mutation; we copy and
        # store as a plain dict — callers are documented to treat as
        # read-only.
        object.__setattr__(self, "fields", dict(self.fields))


@dataclass(frozen=True, slots=True)
class PlanStep:
    """One step in a plan.

    Carries the underlying Action plus optional ordering and
    timing metadata that the plan-evaluator (Phase 3) consumes.
    """

    action: Action
    step_id: str = ""
    """Stable identifier within the plan, optional. Empty string
    means the step is identified by its index."""

    scheduled_duration_s: float = 0.0
    """Caller-declared duration. ``obligate-within`` constraints
    operate on this — the Guard does NOT measure wall-clock time
    (documented in RR-related discussion in Epic 27 spec)."""

    pre_state: StateSnapshot = field(default_factory=StateSnapshot)
    post_state: StateSnapshot = field(default_factory=StateSnapshot)


@dataclass(frozen=True, slots=True)
class Plan:
    """A complete plan, ready for ``Guard.plan_check``.

    ``Plan.from_action(a)`` is the canonical bridge from the Action-
    level API to the Plan-level API: the resulting plan has exactly
    one step whose action is ``a`` unchanged. AEGIS-2701 acceptance
    locks this in as a property test.
    """

    steps: tuple[PlanStep, ...] = ()
    initial_state: StateSnapshot = field(default_factory=StateSnapshot)
    plan_id: str = ""

    @classmethod
    def from_action(cls, action: Action) -> Plan:
        """Build a one-step plan from an Action. The action is stored
        verbatim — by-construction backward compatibility."""
        return cls(steps=(PlanStep(action=action),))

    def to_facts(self) -> list[tuple[Any, ...]]:
        """Project the plan into KB facts.

        Emits one ``("plan", plan_id, step_count)`` fact, one
        ``("planStep", plan_id, index, action_type)`` fact per step,
        plus the underlying action facts via ``Action.to_facts()``.
        """
        facts: list[tuple[Any, ...]] = []
        facts.append(("plan", self.plan_id or "_unnamed", len(self.steps)))
        for index, step in enumerate(self.steps):
            facts.append((
                "planStep", self.plan_id or "_unnamed", index,
                step.action.action_type,
            ))
            facts.extend(step.action.to_facts())
        return facts

    def validate_limits(self) -> list[str]:
        """Return D-007-style limit violations.

        Empty plans pass this check; the *semantic* empty-plan
        rejection happens later in the evaluator with
        ``ViolationType.EMPTY_PLAN``.
        """
        violations: list[str] = []
        if len(self.steps) > MAX_PLAN_STEPS:
            violations.append(
                f"plan has {len(self.steps)} steps (max {MAX_PLAN_STEPS})",
            )
        if len(self.initial_state.fields) > MAX_STATE_FIELDS:
            violations.append(
                f"initial_state has {len(self.initial_state.fields)} fields "
                f"(max {MAX_STATE_FIELDS})",
            )
        # Per-step state caps.
        for index, step in enumerate(self.steps):
            for which, snapshot in (("pre_state", step.pre_state), ("post_state", step.post_state)):
                if len(snapshot.fields) > MAX_STATE_FIELDS:
                    violations.append(
                        f"step[{index}].{which} has {len(snapshot.fields)} "
                        f"fields (max {MAX_STATE_FIELDS})",
                    )
        # Coarse byte-budget guard. The 512 kB number matches
        # MAX_PLAN_SIZE_BYTES; a precise bytesize is overkill — len()
        # of the projected facts list is a deterministic proxy.
        approx_bytes = sum(len(repr(f)) for f in self.to_facts())
        if approx_bytes > MAX_PLAN_SIZE_BYTES:
            violations.append(
                f"plan exceeds {MAX_PLAN_SIZE_BYTES} byte budget "
                f"({approx_bytes} bytes)",
            )
        return violations


@dataclass(frozen=True, slots=True)
class ObligationMatch:
    """One match of a declared obligation against a plan step.

    Used by Phase 3+ (obligation-coverage analysis). Surfaced here as
    a foundational type so downstream tickets don't reinvent it.
    """

    obligation_id: str
    matched_step_index: int
    matched_action_type: str


@dataclass(frozen=True, slots=True)
class ObligationCoverage:
    """Aggregate obligation-coverage report for a plan."""

    matches: tuple[ObligationMatch, ...] = ()
    uncovered_obligation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanViolation:
    """One violation observed by the plan evaluator."""

    violation_type: ViolationType
    step_index: int = -1
    """Step index when applicable; -1 for plan-level violations
    (e.g. AGGREGATE_VIOLATION, OBLIGATION_UNCOVERED)."""

    constraint_id: str = ""
    """Identifier of the declared plan-constraint that triggered."""

    detail: str = ""
    """Human-readable detail for audit + reporting."""
