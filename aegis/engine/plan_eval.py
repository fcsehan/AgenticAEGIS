"""AEGIS-2708 (Epic 27) — Plan-Evaluator Core.

Pure Core-level plan evaluation: per-step delegation to the existing
DDIC evaluators (``evaluate_legacy_module`` / ``evaluate_ddic_module``)
plus a hook for plan-level constraint checks (AEGIS-2709) and
obligation coverage (AEGIS-2710).

This module sits in ``aegis.engine`` and **must not** import from
``aegis.guard``. The Guard-side adapter (``PlanPipeline`` in AEGIS-2710)
does the translation from this Core-result type into a ``PlanVerdict``.
The strict boundary keeps ``aegis-core`` embeddable in any Python
process, the same property that was paid for in v2.0 architecture
separation (``spec/AEGIS_v2_ARCHITECTURE_SEPARATION.md``).

Why a fresh ``PlanView`` type instead of reusing ``aegis.guard.plan.Plan``:
the same boundary. ``Plan`` lives in Guard because it carries
``Action`` (which has Guard-side validation semantics). The Core sees
a thin Engine-level projection — agent + proposition + state field
maps + scheduled duration. AEGIS-2710 builds a ``PlanView`` from a
``Plan`` at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aegis.engine.ddic_eval import (
    DDICBeliefState,
    DDICVerdict,
    build_belief_state,
    evaluate_ddic_module,
    evaluate_legacy_module,
)
from aegis.engine.ddic_ir import (
    DDICCompound,
    DDICInteger,
    DDICModule,
    DDICPlanConstraint,
    DDICSymbol,
    PlanConstraintKind,
)
from aegis.engine.pattern_matcher import FAIL, unify_terms

# AEGIS-2708 acceptance — same numeric ceiling as ``aegis.guard.plan``
# but redefined here because Core cannot import Guard. The Guard side
# enforces the same number; both must move together if relaxed.
MAX_PLAN_STEPS_CORE = 500


class PlanCoreOutcome(Enum):
    """Core-level decision for a whole plan.

    - ``EXECUTABLE``: every step PERMITTED, no plan-level violation.
    - ``BLOCKED``: at least one critical violation (FORBIDDEN step or
      a plan-constraint violation classified critical).
    - ``UNDECIDABLE``: the evaluator cannot certify the plan
      (UNDECIDABLE step, exceeded plan-step budget, etc.).

    The names track Olson's wording (``Ch 6.4``) rather than the Guard
    enum (PERMITTED/FORBIDDEN/UNDECIDABLE) so the Core/Guard boundary
    is visible: the translation lives in ``PlanPipeline`` (AEGIS-2710).
    """

    EXECUTABLE = "EXECUTABLE"
    BLOCKED = "BLOCKED"
    UNDECIDABLE = "UNDECIDABLE"


@dataclass(frozen=True, slots=True)
class PlanStepView:
    """Engine-level projection of a plan step.

    Attributes:
        step_index: 0-based position in the plan.
        action_type: The action-type symbol (Engine-equivalent of
            ``Action.action_type``).
        agent: Agent identifier.
        proposition: Proposition tuple, the same shape Guard hands to
            ``evaluate_legacy_module``.
        scheduled_duration_s: Caller-declared duration. Consumed by
            ``obligate-within`` checks (AEGIS-2709).
        pre_state_fields / post_state_fields: State snapshot maps
            (defensively copied at construction). The evaluator does
            NOT verify state truthfulness — that is the I3 boundary
            documented in the guarantee boundary.
    """

    step_index: int
    action_type: str
    agent: str
    proposition: tuple[object, ...]
    scheduled_duration_s: float = 0.0
    pre_state_fields: dict[str, Any] = field(default_factory=dict)
    post_state_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Make the dicts effectively read-only after construction.
        object.__setattr__(self, "pre_state_fields", dict(self.pre_state_fields))
        object.__setattr__(self, "post_state_fields", dict(self.post_state_fields))


@dataclass(frozen=True, slots=True)
class PlanView:
    """Engine-level projection of a plan.

    The Guard-side ``PlanPipeline`` builds one of these from a
    ``aegis.guard.plan.Plan`` at the boundary; the evaluator works
    only with this type so the import boundary stays clean.
    """

    steps: tuple[PlanStepView, ...]
    initial_state_fields: dict[str, Any] = field(default_factory=dict)
    plan_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "initial_state_fields", dict(self.initial_state_fields))


class PlanCoreViolationKind(Enum):
    """Plan-level violation kinds at the Core layer.

    Mirrors ``aegis.guard.plan.ViolationType`` but lives in Core to
    avoid the import boundary. The Guard-side adapter remaps these
    1:1 to ``ViolationType`` values.
    """

    SEQUENCE = "SEQUENCE_VIOLATION"
    AGGREGATE = "AGGREGATE_VIOLATION"
    TIMING = "TIMING_VIOLATION"
    PRECONDITION = "PRECONDITION_VIOLATION"
    STEP_FORBIDDEN = "STEP_FORBIDDEN"
    STEP_UNDECIDABLE = "STEP_UNDECIDABLE"
    OBLIGATION_UNCOVERED = "OBLIGATION_UNCOVERED"
    EMPTY_PLAN = "EMPTY_PLAN"
    PLAN_TOO_LONG = "PLAN_TOO_LONG"


@dataclass(frozen=True, slots=True)
class PlanCoreViolation:
    """One plan-level violation observed by the Core evaluator."""

    kind: PlanCoreViolationKind
    step_index: int = -1
    constraint_id: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class PlanStepBelief:
    """Per-step Core-level result.

    Carries the BeliefState that the existing DDIC evaluators
    produced, plus a derived ``DDICVerdict`` so AEGIS-2710 can
    aggregate without re-deriving.
    """

    step_index: int
    belief_state: DDICBeliefState
    derived_verdict: DDICVerdict


@dataclass(frozen=True, slots=True)
class CoreObligationMatch:
    """A satisfied obligation paired with the step that satisfies it."""

    formula_id: str
    matched_step_index: int
    matched_action_type: str
    behavior: str


@dataclass(frozen=True, slots=True)
class CoreUnsatisfiedObligation:
    """An obligation that no plan step covers."""

    formula_id: str
    behavior: str
    agent_pattern: str


@dataclass(frozen=True, slots=True)
class CoreObligationCoverage:
    """AEGIS-2710 — Core-side obligation coverage report.

    Always populated by ``evaluate_plan_module``; only converted to
    ``OBLIGATION_UNCOVERED`` violations when
    ``DDICModule.require_obligation_coverage`` is True.
    """

    satisfied: tuple[CoreObligationMatch, ...] = ()
    unsatisfied: tuple[CoreUnsatisfiedObligation, ...] = ()
    inapplicable: tuple[CoreUnsatisfiedObligation, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanEvaluationResult:
    """Aggregate Core-level plan-evaluation result.

    AEGIS-2708 acceptance: this is a pure Core data structure (no
    Guard imports). AEGIS-2710 builds the Guard-side ``PlanVerdict``
    from this.
    """

    overall_outcome: PlanCoreOutcome
    step_beliefs: tuple[PlanStepBelief, ...]
    step_snapshots: tuple[dict[str, Any], ...]
    plan_violations_core: tuple[PlanCoreViolation, ...]
    reason_summary: str = ""
    obligation_coverage: CoreObligationCoverage = field(
        default_factory=lambda: CoreObligationCoverage(),
    )


# ── Public API ─────────────────────────────────────────────────────


def evaluate_plan_module(
    module: DDICModule,
    plan_view: PlanView,
    inheritance: object | None = None,
) -> PlanEvaluationResult:
    """Evaluate a plan against a compiled DDIC module.

    AEGIS-2708 contract:

    - Empty plan → ``BLOCKED`` with a single ``EMPTY_PLAN`` violation.
    - More than ``MAX_PLAN_STEPS_CORE`` steps → ``UNDECIDABLE`` with a
      single ``PLAN_TOO_LONG`` violation referencing residual risk
      ``R-5`` so an auditor can find the limit's rationale.
    - Otherwise: per-step delegation to the existing DDIC evaluators
      (``evaluate_legacy_module`` for v1 modules,
      ``evaluate_ddic_module`` + per-step scoping for v2). A
      coarse step ``DDICVerdict`` is read off the resulting
      ``DDICBeliefState``; FORBIDDEN/UNDECIDABLE steps emit a
      Core violation, but the **plan-level constraint checks**
      and **obligation coverage** land in AEGIS-2709 / 2710. This
      ticket only sets up the dispatch and the empty/too-long
      sentinels.

    The result is deterministic for identical inputs; tests lock that
    in by hashing the result tuples.
    """
    if not plan_view.steps:
        return PlanEvaluationResult(
            overall_outcome=PlanCoreOutcome.BLOCKED,
            step_beliefs=(),
            step_snapshots=(),
            plan_violations_core=(
                PlanCoreViolation(
                    kind=PlanCoreViolationKind.EMPTY_PLAN,
                    detail="empty_plan",
                ),
            ),
            reason_summary="empty_plan",
        )

    if len(plan_view.steps) > MAX_PLAN_STEPS_CORE:
        return PlanEvaluationResult(
            overall_outcome=PlanCoreOutcome.UNDECIDABLE,
            step_beliefs=(),
            step_snapshots=(),
            plan_violations_core=(
                PlanCoreViolation(
                    kind=PlanCoreViolationKind.PLAN_TOO_LONG,
                    detail=(
                        f"plan has {len(plan_view.steps)} steps, max "
                        f"{MAX_PLAN_STEPS_CORE} (residual risk R-5)"
                    ),
                ),
            ),
            reason_summary="plan_too_long",
        )

    is_legacy = module.resolution_strategy == "legacy"
    # v2 path: evaluate the module once and reuse runtime per step.
    cached_runtime = None if is_legacy else evaluate_ddic_module(module)

    step_beliefs: list[PlanStepBelief] = []
    step_snapshots: list[dict[str, Any]] = []
    violations: list[PlanCoreViolation] = []

    # Track a running state snapshot. The evaluator does not enforce
    # state-progression semantics yet — that is AEGIS-2709's job for
    # ``require-precondition``. For now we record per-step pre_state
    # so 2709 can read it without re-walking the plan.
    running_state: dict[str, Any] = dict(plan_view.initial_state_fields)

    for step in plan_view.steps:
        # Step-state computation: pre_state-fields override running
        # state; post_state fields then update for the next step.
        merged_pre = dict(running_state)
        merged_pre.update(step.pre_state_fields)
        step_snapshots.append(dict(merged_pre))

        belief_state = _evaluate_step(
            module, step, inheritance, cached_runtime, is_legacy
        )
        derived = belief_state.verdict
        step_beliefs.append(
            PlanStepBelief(
                step_index=step.step_index,
                belief_state=belief_state,
                derived_verdict=derived,
            )
        )

        if derived == DDICVerdict.FORBIDDEN:
            violations.append(
                PlanCoreViolation(
                    kind=PlanCoreViolationKind.STEP_FORBIDDEN,
                    step_index=step.step_index,
                    detail=f"step {step.step_index} ({step.action_type}) FORBIDDEN",
                )
            )
        elif derived == DDICVerdict.UNDECIDABLE:
            violations.append(
                PlanCoreViolation(
                    kind=PlanCoreViolationKind.STEP_UNDECIDABLE,
                    step_index=step.step_index,
                    detail=f"step {step.step_index} ({step.action_type}) UNDECIDABLE",
                )
            )

        # AEGIS-2709: per-step precondition checks see the merged_pre
        # snapshot for THIS step, before any post-state updates.
        violations.extend(
            _check_preconditions_for_step(
                module.plan_constraints, step, merged_pre,
            )
        )

        # Update running state for the next step.
        running_state.update(step.post_state_fields)

    # AEGIS-2709: plan-level constraint checks that need the whole
    # step sequence (sequence, aggregate, within). These run AFTER
    # per-step delegation so step indices and durations are stable.
    violations.extend(_check_obligate_sequence(
        module.plan_constraints, plan_view,
    ))
    violations.extend(_check_forbid_aggregate(
        module.plan_constraints, plan_view,
    ))
    violations.extend(_check_obligate_within(
        module.plan_constraints, plan_view,
    ))

    # AEGIS-2710: obligation coverage. Always computed so callers
    # can inspect satisfied/unsatisfied; only emits OBLIGATION_UNCOVERED
    # violations when ``module.require_obligation_coverage`` is True.
    coverage = _compute_obligation_coverage(module, plan_view)
    if module.require_obligation_coverage:
        for unsat in coverage.unsatisfied:
            violations.append(
                PlanCoreViolation(
                    kind=PlanCoreViolationKind.OBLIGATION_UNCOVERED,
                    constraint_id=unsat.formula_id,
                    detail=(
                        f"obligation {unsat.formula_id} ({unsat.behavior!r}) "
                        f"not covered by any step in this plan"
                    ),
                )
            )

    overall = _aggregate_outcome(violations)
    summary = _violation_summary(violations)
    return PlanEvaluationResult(
        overall_outcome=overall,
        step_beliefs=tuple(step_beliefs),
        step_snapshots=tuple(step_snapshots),
        plan_violations_core=tuple(violations),
        reason_summary=summary,
        obligation_coverage=coverage,
    )


# ── Helpers ────────────────────────────────────────────────────────


def _evaluate_step(
    module: DDICModule,
    step: PlanStepView,
    inheritance: object | None,
    cached_runtime: object | None,
    is_legacy: bool,
) -> DDICBeliefState:
    """Delegate to the existing DDIC evaluator for one step.

    The dispatch matches ``EvaluationPipeline._evaluate_via_module``
    in spirit but stays Core-pure (no Verdict construction).
    """
    if is_legacy:
        return evaluate_legacy_module(
            module, step.proposition, step.agent, inheritance
        )
    # v2 path: scope the cached runtime to this step's belief.
    assert cached_runtime is not None
    return _scope_runtime_to_step(cached_runtime, step)


def _scope_runtime_to_step(runtime: object, step: PlanStepView) -> DDICBeliefState:
    """Extract a step-scoped BeliefState from a v2 runtime.

    The full v2 belief-state is module-wide. For per-step plan
    evaluation we need the subset whose behavior matches the step's
    proposition / agent. Mirrors
    ``EvaluationPipeline._scope_belief_state`` but Core-only — no
    Action import.
    """
    full_state = build_belief_state(runtime)  # type: ignore[arg-type]
    target_behavior = _proposition_to_term(step.proposition)
    target_agent = step.agent

    scoped_active = tuple(
        derived for derived in full_state.active_beliefs
        if _agent_matches(derived.formula.agent, target_agent)
        and _behavior_matches(derived.formula.behavior, target_behavior)
    )
    scoped_defeated = tuple(
        derived for derived in full_state.defeated_beliefs
        if _agent_matches(derived.formula.agent, target_agent)
        and _behavior_matches(derived.formula.behavior, target_behavior)
    )

    if not scoped_active and not scoped_defeated:
        return DDICBeliefState(
            active_beliefs=(),
            defeated_beliefs=(),
            unresolved_conflicts=(),
            verdict=DDICVerdict.UNDECIDABLE,
            defeats=(),
        )

    # Re-derive verdict from the scoped active beliefs only. We reuse
    # the same logic the full belief-state used (any FORBIDDEN among
    # actives → FORBIDDEN, any OBLIGATORY → PERMITTED, otherwise
    # PERMITTED if at least one active OPTIONAL belief remains).
    return DDICBeliefState(
        active_beliefs=scoped_active,
        defeated_beliefs=scoped_defeated,
        unresolved_conflicts=full_state.unresolved_conflicts,
        verdict=_verdict_from_scoped(scoped_active),
        defeats=full_state.defeats,
    )


def _proposition_to_term(prop: tuple[object, ...]) -> object:
    """Map a v1-style proposition tuple to a DDIC term for matching.

    Mirrors ``aegis.engine.normframe_compile._proposition_to_behavior``
    but local to the evaluator so the import surface stays small.
    """
    if len(prop) == 0:
        return DDICSymbol("")
    if len(prop) == 1:
        return DDICSymbol(str(prop[0]))
    head = str(prop[0])
    args = tuple(DDICSymbol(str(arg)) for arg in prop[1:])
    return DDICCompound(head=head, args=args)


def _agent_matches(formula_agent: object, requested_agent: str) -> bool:
    """Wildcard-aware agent match (Core-local; mirrors NormFrame.matches_agent)."""
    if isinstance(formula_agent, DDICSymbol):
        return formula_agent.value in {"*", requested_agent}
    return False


def _behavior_matches(formula_behavior: object, target: object) -> bool:
    """Behavior match for scoping a v2 belief state to one step.

    Exact-equality first; then symbol-equals-compound-head case for
    the one-arity proposition case (matches the v1 path's behavior).
    """
    if formula_behavior == target:
        return True
    if isinstance(formula_behavior, DDICSymbol) and isinstance(target, DDICCompound):
        return formula_behavior.value == target.head
    if isinstance(formula_behavior, DDICCompound) and isinstance(target, DDICSymbol):
        return formula_behavior.head == target.value
    return False


def _verdict_from_scoped(active_beliefs: tuple[Any, ...]) -> DDICVerdict:
    """Derive a DDICVerdict from a scoped set of active beliefs."""
    if not active_beliefs:
        return DDICVerdict.UNDECIDABLE
    modes = {derived.formula.mode.value for derived in active_beliefs}
    if "forbidden" in modes:
        return DDICVerdict.FORBIDDEN
    if "obligatory" in modes or "optional" in modes:
        return DDICVerdict.PERMITTED
    return DDICVerdict.UNDECIDABLE


# ── AEGIS-2709: Plan-Constraint Checks ─────────────────────────────


def _check_obligate_sequence(
    constraints: tuple[DDICPlanConstraint, ...],
    plan_view: PlanView,
) -> list[PlanCoreViolation]:
    """Topological sequence check.

    For each ``obligate-sequence A B``: if both A and B occur in the
    plan, every occurrence of B must come after at least one
    occurrence of A. A plan with only A (or only B) does NOT trigger
    a violation — the constraint is conditional on co-occurrence.
    """
    violations: list[PlanCoreViolation] = []
    # Index of every action-type's first appearance for fast lookup.
    type_indices: dict[str, list[int]] = {}
    for step in plan_view.steps:
        type_indices.setdefault(step.action_type, []).append(step.step_index)

    for c in constraints:
        if c.kind != PlanConstraintKind.OBLIGATE_SEQUENCE:
            continue
        if len(c.args) != 2:
            continue
        head, tail = c.args
        if not (isinstance(head, DDICSymbol) and isinstance(tail, DDICSymbol)):
            continue
        a_indices = type_indices.get(head.value, [])
        b_indices = type_indices.get(tail.value, [])
        if not a_indices or not b_indices:
            continue
        first_a = min(a_indices)
        # Every B before any A is a violation.
        for b_idx in b_indices:
            if b_idx < first_a:
                violations.append(
                    PlanCoreViolation(
                        kind=PlanCoreViolationKind.SEQUENCE,
                        step_index=b_idx,
                        constraint_id=c.constraint_id,
                        detail=(
                            f"{tail.value} at index {b_idx} occurs before "
                            f"any {head.value} (constraint {c.constraint_id})"
                        ),
                    )
                )
    return violations


def _check_forbid_aggregate(
    constraints: tuple[DDICPlanConstraint, ...],
    plan_view: PlanView,
) -> list[PlanCoreViolation]:
    """Counting check.

    For each ``forbid-aggregate A N``: count the number of plan steps
    whose action_type is A. If count > N, report one AGGREGATE
    violation referencing the constraint and the offending count.
    Threshold N == 0 forbids the action entirely; ANY occurrence
    yields a violation. Plans without A are unaffected.
    """
    violations: list[PlanCoreViolation] = []
    counts: dict[str, list[int]] = {}
    for step in plan_view.steps:
        counts.setdefault(step.action_type, []).append(step.step_index)

    for c in constraints:
        if c.kind != PlanConstraintKind.FORBID_AGGREGATE:
            continue
        if len(c.args) != 2:
            continue
        action_term, threshold_term = c.args
        if not (
            isinstance(action_term, DDICSymbol)
            and isinstance(threshold_term, DDICInteger)
        ):
            continue
        indices = counts.get(action_term.value, [])
        count = len(indices)
        if count > threshold_term.value:
            # Locate the first offending step (index just past the
            # threshold) so the diagnostic points to the violator,
            # not to step 0.
            offending_index = (
                indices[threshold_term.value]
                if threshold_term.value < count
                else indices[-1]
            )
            violations.append(
                PlanCoreViolation(
                    kind=PlanCoreViolationKind.AGGREGATE,
                    step_index=offending_index,
                    constraint_id=c.constraint_id,
                    detail=(
                        f"{action_term.value} appears {count} times "
                        f"(max {threshold_term.value}) — first excess at "
                        f"step {offending_index}"
                    ),
                )
            )
    return violations


def _check_obligate_within(
    constraints: tuple[DDICPlanConstraint, ...],
    plan_view: PlanView,
) -> list[PlanCoreViolation]:
    """Timing check.

    Two semantics keyed off ``obligate-within``'s second arg:

    - ``immediate``: the action must be at index 0 of the plan;
      otherwise emit a TIMING violation pointing at the first
      occurrence.
    - integer N: the cumulative ``scheduled_duration_s`` of every
      step strictly **before** the action's first occurrence must
      be ≤ N. ``same-session`` and ``end-of-plan`` are accepted
      as no-op timings at this layer (the symbols are
      session-level, not within a single plan); they are not
      enforced here. AEGIS-2709 covers within-plan enforcement only.

    Plans without the named action are unaffected.
    """
    violations: list[PlanCoreViolation] = []
    first_occurrence: dict[str, int] = {}
    cumulative_before: dict[str, float] = {}
    cumulative = 0.0
    for step in plan_view.steps:
        if step.action_type not in first_occurrence:
            first_occurrence[step.action_type] = step.step_index
            cumulative_before[step.action_type] = cumulative
        cumulative += step.scheduled_duration_s

    for c in constraints:
        if c.kind != PlanConstraintKind.OBLIGATE_WITHIN:
            continue
        if len(c.args) != 2:
            continue
        action_term, timeframe = c.args
        if not isinstance(action_term, DDICSymbol):
            continue
        if action_term.value not in first_occurrence:
            continue
        idx = first_occurrence[action_term.value]
        if isinstance(timeframe, DDICSymbol) and timeframe.value == "immediate":
            if idx != 0:
                violations.append(
                    PlanCoreViolation(
                        kind=PlanCoreViolationKind.TIMING,
                        step_index=idx,
                        constraint_id=c.constraint_id,
                        detail=(
                            f"{action_term.value} required at index 0 "
                            f"(immediate), found first at index {idx}"
                        ),
                    )
                )
            continue
        if isinstance(timeframe, DDICInteger):
            preceding = cumulative_before[action_term.value]
            if preceding > timeframe.value:
                violations.append(
                    PlanCoreViolation(
                        kind=PlanCoreViolationKind.TIMING,
                        step_index=idx,
                        constraint_id=c.constraint_id,
                        detail=(
                            f"{action_term.value} preceded by "
                            f"{preceding}s of duration (max "
                            f"{timeframe.value}s) — constraint "
                            f"{c.constraint_id}"
                        ),
                    )
                )
            continue
        # ``same-session`` / ``end-of-plan`` are session-level and
        # not enforceable on a single plan view; the verifier
        # accepts them but the plan-evaluator treats them as
        # always-satisfied at this layer.
    return violations


def _check_preconditions_for_step(
    constraints: tuple[DDICPlanConstraint, ...],
    step: PlanStepView,
    pre_state: dict[str, Any],
) -> list[PlanCoreViolation]:
    """``require-precondition`` check for one step.

    For each ``require-precondition ?action-type ?precondition`` whose
    action-type matches the step, evaluate the precondition pattern
    against the step's pre-state snapshot. The precondition is a
    DDICCompound like ``(testStatus passed)``; matching is done by
    looking up the head in ``pre_state`` and comparing values via
    ``unify_terms``.
    """
    violations: list[PlanCoreViolation] = []
    for c in constraints:
        if c.kind != PlanConstraintKind.REQUIRE_PRECONDITION:
            continue
        if len(c.args) != 2:
            continue
        action_term, precond = c.args
        if not isinstance(action_term, DDICSymbol):
            continue
        if action_term.value != step.action_type:
            continue
        if not _precondition_holds(precond, pre_state):
            violations.append(
                PlanCoreViolation(
                    kind=PlanCoreViolationKind.PRECONDITION,
                    step_index=step.step_index,
                    constraint_id=c.constraint_id,
                    detail=(
                        f"{step.action_type} precondition not met at step "
                        f"{step.step_index}: required {_repr_term(precond)}, "
                        f"state has {pre_state}"
                    ),
                )
            )
    return violations


def _precondition_holds(precond: object, pre_state: dict[str, Any]) -> bool:
    """Evaluate a precondition pattern against the pre-state.

    Two shapes accepted:

    - ``(predicate value)``: the state must have an entry whose key
      equals ``predicate`` and whose value equals ``value`` (after
      DDICTerm unification).
    - ``(predicate arg1 arg2)``: the state must hold a tuple/list at
      key ``predicate`` whose element-wise unification with the
      remaining args succeeds.
    - DDICSymbol on its own: the state must have that symbol as a
      truthy entry (used for boolean flags like ``"passed"``).
    """
    if isinstance(precond, DDICSymbol):
        return bool(pre_state.get(precond.value))
    if isinstance(precond, DDICCompound):
        head = precond.head
        if head not in pre_state:
            return False
        state_value = pre_state[head]
        if len(precond.args) == 1:
            target = _value_to_term(state_value)
            return unify_terms(precond.args[0], target) is not FAIL
        if isinstance(state_value, (tuple, list)):
            if len(state_value) != len(precond.args):
                return False
            for arg, sval in zip(precond.args, state_value, strict=True):
                if unify_terms(arg, _value_to_term(sval)) is FAIL:
                    return False
            return True
        return False
    return False


def _value_to_term(value: object) -> object:
    """Wrap a Python value as a DDICTerm so unify_terms can compare."""
    if isinstance(value, bool):
        return DDICSymbol("true" if value else "false")
    if isinstance(value, int):
        return DDICInteger(value)
    if isinstance(value, str):
        return DDICSymbol(value)
    return DDICSymbol(str(value))


def _repr_term(term: object) -> str:
    if isinstance(term, DDICSymbol):
        return term.value
    if isinstance(term, DDICInteger):
        return str(term.value)
    if isinstance(term, DDICCompound):
        inner = " ".join(_repr_term(a) for a in term.args)
        return f"({term.head} {inner})"
    return repr(term)


# ── AEGIS-2710: Obligation Coverage ───────────────────────────────


def _compute_obligation_coverage(
    module: DDICModule,
    plan_view: PlanView,
) -> CoreObligationCoverage:
    """For each OBLIGATORY+TESTIMONY formula, find a covering step.

    Coverage rule (best-effort, AEGIS-2710 acceptance):

    - The formula's agent_pattern must match at least one step's agent
      (wildcard ``"*"`` matches any).
    - One of the agent-matching steps must also match the formula's
      behavior (action_type symbol or compound head).
    - When at least one agent matches but no behavior matches:
      ``unsatisfied``.
    - When no agent in the plan matches: ``inapplicable`` (the
      obligation isn't aimed at any actor in this plan).
    """
    satisfied: list[CoreObligationMatch] = []
    unsatisfied: list[CoreUnsatisfiedObligation] = []
    inapplicable: list[CoreUnsatisfiedObligation] = []

    for formula in module.formulas:
        if formula.mode.value != "obligatory":
            continue
        if formula.layer.value != "testimony":
            continue
        agent_pattern = (
            formula.agent.value
            if isinstance(formula.agent, DDICSymbol)
            else "*"
        )
        behavior_label = _behavior_label(formula.behavior)
        agent_matching_steps = [
            step for step in plan_view.steps
            if agent_pattern == "*" or agent_pattern == step.agent
        ]
        if not agent_matching_steps:
            inapplicable.append(
                CoreUnsatisfiedObligation(
                    formula_id=formula.formula_id,
                    behavior=behavior_label,
                    agent_pattern=agent_pattern,
                )
            )
            continue
        match_step: PlanStepView | None = None
        for step in agent_matching_steps:
            if _step_covers_behavior(step, formula.behavior):
                match_step = step
                break
        if match_step is not None:
            satisfied.append(
                CoreObligationMatch(
                    formula_id=formula.formula_id,
                    matched_step_index=match_step.step_index,
                    matched_action_type=match_step.action_type,
                    behavior=behavior_label,
                )
            )
        else:
            unsatisfied.append(
                CoreUnsatisfiedObligation(
                    formula_id=formula.formula_id,
                    behavior=behavior_label,
                    agent_pattern=agent_pattern,
                )
            )

    return CoreObligationCoverage(
        satisfied=tuple(satisfied),
        unsatisfied=tuple(unsatisfied),
        inapplicable=tuple(inapplicable),
    )


def _behavior_label(term: object) -> str:
    if isinstance(term, DDICSymbol):
        return term.value
    if isinstance(term, DDICCompound):
        return term.head
    return str(term)


def _step_covers_behavior(step: PlanStepView, behavior: object) -> bool:
    """A step covers a behavior when its action_type or proposition
    head equals the behavior's symbol/head."""
    if isinstance(behavior, DDICSymbol):
        target = behavior.value
    elif isinstance(behavior, DDICCompound):
        target = behavior.head
    else:
        return False
    if step.action_type == target:
        return True
    return bool(step.proposition) and str(step.proposition[0]) == target


def _aggregate_outcome(
    violations: list[PlanCoreViolation],
) -> PlanCoreOutcome:
    """Aggregate per-step + plan-level violations into one outcome.

    Phase 3 rule:
    - Any STEP_FORBIDDEN → BLOCKED.
    - Any STEP_UNDECIDABLE without FORBIDDEN → UNDECIDABLE.
    - Otherwise EXECUTABLE.

    AEGIS-2709 will extend this with sequence/aggregate/timing/
    precondition violations (all BLOCKED) and AEGIS-2710 with
    obligation-uncovered (BLOCKED only when
    ``require_obligation_coverage`` is True).
    """
    blocking_kinds = {
        PlanCoreViolationKind.STEP_FORBIDDEN,
        PlanCoreViolationKind.SEQUENCE,
        PlanCoreViolationKind.AGGREGATE,
        PlanCoreViolationKind.TIMING,
        PlanCoreViolationKind.PRECONDITION,
        PlanCoreViolationKind.OBLIGATION_UNCOVERED,
    }
    if any(v.kind in blocking_kinds for v in violations):
        return PlanCoreOutcome.BLOCKED
    if any(v.kind == PlanCoreViolationKind.STEP_UNDECIDABLE for v in violations):
        return PlanCoreOutcome.UNDECIDABLE
    return PlanCoreOutcome.EXECUTABLE


def _violation_summary(violations: list[PlanCoreViolation]) -> str:
    """Produce a short machine-readable summary of the dominant
    violation reason. Empty when there are no violations."""
    if not violations:
        return ""
    # Stable selection: first violation's kind drives the summary.
    return violations[0].kind.value.lower()


__all__ = [
    "MAX_PLAN_STEPS_CORE",
    "CoreObligationCoverage",
    "CoreObligationMatch",
    "CoreUnsatisfiedObligation",
    "PlanCoreOutcome",
    "PlanCoreViolation",
    "PlanCoreViolationKind",
    "PlanEvaluationResult",
    "PlanStepBelief",
    "PlanStepView",
    "PlanView",
    "evaluate_plan_module",
]
