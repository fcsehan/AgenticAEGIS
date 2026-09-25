"""Initial DDIC evaluation over compiled IR.

This module implements the first executable layer for AEGIS-2305:
- asserted formulas
- categorical defaults
- defeasible rule application
- basic conflict classification
- basic Lex Posterior defeat for complete-defeat cases
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aegis.engine.ddic_ir import (
    DDICCompound,
    DDICCondition,
    DDICDefeasibleRule,
    DDICDefeatMode,
    DDICFormula,
    DDICFormulaPattern,
    DDICInteger,
    DDICMetadata,
    DDICModule,
    DDICPatternTerm,
    DDICPriorityEdge,
    DDICRelation,
    DDICRelationKind,
    DDICSymbol,
    DDICVar,
    FormulaCondition,
    PredicateCondition,
    RelationCondition,
)


class DerivationOrigin(Enum):
    ASSERTED = "asserted"
    CATEGORICAL_DEFAULT = "categorical_default"
    DEFEASIBLE_RULE = "defeasible_rule"


class DefeatReason(Enum):
    PRIORITY = "priority"
    LEX_POSTERIOR = "lex_posterior"
    INCONSISTENT_TESTIMONY = "inconsistent_testimony"
    SPECIFIC_EXCEPTION = "specific_exception"


class ConflictType(Enum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    INTERSECTING = "intersecting"


class DDICVerdict(Enum):
    PERMITTED = "permitted"
    FORBIDDEN = "forbidden"
    UNDECIDABLE = "undecidable"


@dataclass(frozen=True, slots=True)
class DerivedFormula:
    formula: DDICFormula
    derivation_id: str
    origin: DerivationOrigin
    support: tuple[str, ...]
    rule_id: str | None = None


@dataclass
class DefeatEvent:
    defeated_derivation_id: str
    defeating_formula_id: str
    defeating_rule_id: str | None
    mode: str
    reason: DefeatReason


@dataclass(frozen=True, slots=True)
class Justification:
    derivation_id: str
    rule_id: str | None
    premises: tuple[str, ...]
    conclusion_formula_id: str


@dataclass(frozen=True, slots=True)
class ConflictEvent:
    left_formula_id: str
    right_formula_id: str
    conflict_type: ConflictType
    shared_behavior: object | None
    shared_context: object | None


@dataclass
class DDICRuntime:
    world: DDICModule
    inferred_formulas: list[DerivedFormula]
    justifications: list[Justification]
    active_formulas: list[DerivedFormula]
    defeated_formulas: list[DerivedFormula]
    defeats: list[DefeatEvent]
    conflicts: list[ConflictEvent]


@dataclass(frozen=True, slots=True)
class DDICBeliefState:
    active_beliefs: tuple[DerivedFormula, ...]
    defeated_beliefs: tuple[DerivedFormula, ...]
    unresolved_conflicts: tuple[ConflictEvent, ...]
    verdict: DDICVerdict
    # Defeat events that produced ``defeated_beliefs``. Each event names
    # the defeating formula/rule, the defeat mode (``complete``/``partial``),
    # and the structured reason (priority / lex_posterior / specific_exception
    # / inconsistent_testimony). Populated by ``build_belief_state``.
    # Required by AEGIS-2306 acceptance criterion #6: defeats must be part
    # of the auditable justification chain, not only a runtime side-log.
    defeats: tuple[DefeatEvent, ...] = ()


Bindings = dict[str, object]


def evaluate_ddic_module(module: DDICModule) -> DDICRuntime:
    """Evaluate compiled DDIC IR.

    This implementation materializes asserted formulas, categorical defaults,
    defeasible-rule candidates, classifies basic conflicts, and applies a
    minimal Lex Posterior defeat for complete-defeat cases.
    """
    runtime = DDICRuntime(
        world=module,
        inferred_formulas=[],
        justifications=[],
        active_formulas=[],
        defeated_formulas=[],
        defeats=[],
        conflicts=[],
    )
    seen: set[DDICFormula] = set()

    for formula in module.formulas:
        runtime.inferred_formulas.append(_asserted_formula(formula))
        seen.add(formula)

    base_formulas = tuple(runtime.inferred_formulas)

    for rule in module.defaults:
        for candidate in _apply_rule_body(rule.body, base_formulas, module.relations):
            derived = _instantiate_rule_head(rule.head, candidate, rule.rule_id, rule.source_ref)
            if derived not in seen:
                seen.add(derived)
                runtime.inferred_formulas.append(
                    DerivedFormula(
                        formula=derived,
                        derivation_id=f"{rule.rule_id}:{len(runtime.inferred_formulas)}",
                        origin=DerivationOrigin.CATEGORICAL_DEFAULT,
                        support=tuple(candidate["_support"]),
                        rule_id=rule.rule_id,
                    )
                )
                runtime.justifications.append(
                    Justification(
                        derivation_id=runtime.inferred_formulas[-1].derivation_id,
                        rule_id=rule.rule_id,
                        premises=tuple(candidate["_support"]),
                        conclusion_formula_id=derived.formula_id,
                    )
                )

    current_formulas = tuple(runtime.inferred_formulas)
    for rule in module.defeasible_rules:
        for candidate in _apply_defeasible_rule(rule, current_formulas, module.relations):
            derived = _instantiate_formula_pattern(
                rule.consequent,
                candidate,
                source_ref=rule.source_ref,
                formula_id=f"{rule.rule_id}:{len(runtime.inferred_formulas)}",
            )
            if derived not in seen:
                seen.add(derived)
                runtime.inferred_formulas.append(
                    DerivedFormula(
                        formula=derived,
                        derivation_id=derived.formula_id,
                        origin=DerivationOrigin.DEFEASIBLE_RULE,
                        support=tuple(candidate["_support"]),
                        rule_id=rule.rule_id,
                    )
                )
                runtime.justifications.append(
                    Justification(
                        derivation_id=derived.formula_id,
                        rule_id=rule.rule_id,
                        premises=tuple(candidate["_support"]),
                        conclusion_formula_id=derived.formula_id,
                    )
                )

    runtime.conflicts = _classify_conflicts(runtime.inferred_formulas, module.relations)
    runtime.active_formulas = list(runtime.inferred_formulas)
    _apply_priority_defeat(runtime, module.priorities)
    _apply_lex_posterior_defeat(runtime, module.relations, module.defeasible_rules)
    return runtime


def build_belief_state(runtime: DDICRuntime) -> DDICBeliefState:
    active_beliefs = tuple(
        derived for derived in runtime.active_formulas if derived.formula.layer.value == "belief"
    )
    defeated_beliefs = tuple(
        derived for derived in runtime.defeated_formulas if derived.formula.layer.value == "belief"
    )
    unresolved_conflicts = tuple(_classify_active_belief_conflicts(active_beliefs, runtime.world.relations))
    verdict = _verdict_from_active_beliefs(active_beliefs, unresolved_conflicts)
    # Only carry defeats that map to a belief-layer derivation — testimony-
    # internal defeats are evaluator-internal and not part of the audit
    # chain at the guard surface.
    defeated_belief_ids = {derived.derivation_id for derived in defeated_beliefs}
    defeats = tuple(
        event for event in runtime.defeats
        if event.defeated_derivation_id in defeated_belief_ids
    )
    return DDICBeliefState(
        active_beliefs=active_beliefs,
        defeated_beliefs=defeated_beliefs,
        unresolved_conflicts=unresolved_conflicts,
        verdict=verdict,
        defeats=defeats,
    )


# ── Legacy v1 6-step evaluation ─────────────────────────────────────


# AEGIS-1901: Documented safety limit (same as v1 DDICEngine).
_MAX_APPLICABLE = 10_000


def evaluate_legacy_module(
    module: DDICModule,
    proposition: tuple[object, ...],
    agent: str,
    inheritance: object | None = None,
) -> DDICBeliefState:
    """Evaluate a v1-compiled DDICModule using the legacy 6-step DDIC algorithm.

    This is the port of DDICEngine.evaluate() operating on DDICFormulas instead
    of NormFrames.  It produces a DDICBeliefState (same output type as the v2
    path) so the unified pipeline can use a single Verdict adapter.

    Steps:
      1. Filter applicable formulas (agent + behavior prefix match)
      2. Moral axioms (is_axiom metadata) win immediately
      3. Sort by specificity (requires InheritanceGraph or metadata)
      4. Preemption: more-specific defeats less-specific
      5. Cross-code prevalence breaks remaining ties
      6. Unresolvable → UNDECIDABLE

    Args:
        module: DDICModule with resolution_strategy="legacy".
        proposition: Action proposition tuple to evaluate.
        agent: Agent ID requesting the action.
        inheritance: Optional InheritanceGraph for specificity lookup.
    """
    chain: list[str] = []

    # Build metadata index.
    axiom_ids = _axiom_formula_ids(module)
    code_map = _formula_code_map(module)

    # Step 1: Filter applicable formulas.
    applicable = [
        f for f in module.formulas
        if _agent_matches(f, agent) and _behavior_matches(f, proposition)
    ]
    chain.append(f"Applicable formulas for agent={agent!r}: {len(applicable)}")

    if len(applicable) > _MAX_APPLICABLE:
        return DDICBeliefState(
            active_beliefs=(),
            defeated_beliefs=(),
            unresolved_conflicts=(),
            verdict=DDICVerdict.UNDECIDABLE,
        )

    if not applicable:
        return DDICBeliefState(
            active_beliefs=(),
            defeated_beliefs=(),
            unresolved_conflicts=(),
            verdict=DDICVerdict.UNDECIDABLE,
        )

    # Step 2: Moral axioms win absolutely.
    axioms = [f for f in applicable if f.formula_id in axiom_ids]
    defeasible = [f for f in applicable if f.formula_id not in axiom_ids]

    if axioms:
        chain.append(f"Moral axioms found: {len(axioms)}")
        axiom_modes = {f.mode for f in axioms}
        if len(axiom_modes) > 1 and _any_modes_conflict(axiom_modes):
            return DDICBeliefState(
                active_beliefs=tuple(_asserted_formula(f) for f in axioms),
                defeated_beliefs=tuple(_asserted_formula(f) for f in defeasible),
                unresolved_conflicts=(),
                verdict=DDICVerdict.UNDECIDABLE,
            )
        return _belief_state_from_winner(axioms[0].mode, axioms, defeasible)

    # Step 3: Sort by specificity.
    prevalence = module.code_prevalence
    spec_map = _formula_specificity_map(module, inheritance)

    def sort_key(f: DDICFormula) -> tuple[int, int, str, str]:
        spec = spec_map.get(f.formula_id, 0)
        code = code_map.get(f.formula_id, "")
        code_rank = 0
        if code and code in prevalence:
            code_rank = len(prevalence) - list(prevalence).index(code)
        return (spec, code_rank, code, f.mode.value)

    sorted_formulas = sorted(defeasible, key=sort_key, reverse=True)
    chain.append(f"Sorted {len(sorted_formulas)} defeasible formulas by specificity")

    # Step 4: Preemption.
    surviving, defeated = _legacy_preemption(sorted_formulas, spec_map)
    chain.append(f"After preemption: {len(surviving)} surviving, {len(defeated)} defeated")

    if not surviving:
        return DDICBeliefState(
            active_beliefs=(),
            defeated_beliefs=tuple(_asserted_formula(f) for f in defeated),
            unresolved_conflicts=(),
            verdict=DDICVerdict.UNDECIDABLE,
        )

    # Check unanimity.
    surviving_modes = {f.mode for f in surviving}
    if len(surviving_modes) == 1:
        return _belief_state_from_winner(surviving[0].mode, surviving, defeated)

    # Step 5: Cross-code prevalence.
    if prevalence:
        resolved = _legacy_resolve_by_prevalence(surviving, code_map, prevalence)
        if resolved is not None:
            winner_mode = resolved[0].mode
            losers = [f for f in surviving if f.mode != winner_mode]
            return _belief_state_from_winner(winner_mode, resolved, defeated + losers)

    # Step 6: Unresolvable.
    return DDICBeliefState(
        active_beliefs=tuple(_asserted_formula(f) for f in surviving),
        defeated_beliefs=tuple(_asserted_formula(f) for f in defeated),
        unresolved_conflicts=(),
        verdict=DDICVerdict.UNDECIDABLE,
    )


def _agent_matches(formula: DDICFormula, agent: str) -> bool:
    if isinstance(formula.agent, DDICSymbol):
        return formula.agent.value == "*" or formula.agent.value == agent
    return False


def _behavior_matches(formula: DDICFormula, proposition: tuple[object, ...]) -> bool:
    """Check if a formula's behavior matches a proposition.

    Mirrors v1 DDICEngine._proposition_matches() semantics:
    1. Try exact unification (same structure, same length)
    2. If behavior is shorter: try unifying behavior against proposition prefix
    """
    from aegis.engine.ddic_ir import DDICCompound
    from aegis.engine.pattern_matcher import FAIL, proposition_to_term, unify_terms

    prop_term = proposition_to_term(proposition)
    # Try exact unification.
    result = unify_terms(formula.behavior, prop_term)
    if result is not FAIL:
        return True
    # Prefix fallback: only when behavior has fewer components than proposition.
    # A DDICSymbol (1 element) is always shorter than a multi-arg proposition.
    # A DDICCompound with N args is shorter than a proposition with >N+1 elements.
    behavior = formula.behavior
    if isinstance(behavior, DDICSymbol):
        behavior_len = 1
    elif isinstance(behavior, DDICCompound):
        behavior_len = 1 + len(behavior.args)
    else:
        return False
    if behavior_len < len(proposition):
        trimmed = proposition_to_term(proposition[:behavior_len])
        result = unify_terms(behavior, trimmed)
        return result is not FAIL
    return False


def _axiom_formula_ids(module: DDICModule) -> frozenset[str]:
    return frozenset(
        m.source_ref for m in module.metadata if m.key == "is_axiom"
    )


def _formula_code_map(module: DDICModule) -> dict[str, str]:
    result: dict[str, str] = {}
    for m in module.metadata:
        if m.key == "code" and isinstance(m.value, DDICSymbol):
            result[m.source_ref] = m.value.value
    return result


def _formula_specificity_map(module: DDICModule, inheritance: object | None) -> dict[str, int]:
    """Build a map of formula_id → specificity, from metadata then InheritanceGraph."""
    result: dict[str, int] = {}
    # First: pre-computed specificity from metadata (set during v1 compilation)
    for m in module.metadata:
        if m.key == "specificity" and isinstance(m.value, DDICSymbol):
            try:
                result[m.source_ref] = int(m.value.value)
            except ValueError:
                pass
    # Second: fill gaps from InheritanceGraph
    if inheritance is not None:
        for f in module.formulas:
            if f.formula_id not in result:
                agent_val = f.agent.value if isinstance(f.agent, DDICSymbol) else ""
                result[f.formula_id] = inheritance.specificity_of(agent_val)  # type: ignore[union-attr]
    return result


def _formula_specificity(formula: DDICFormula, inheritance: object | None) -> int:
    if inheritance is None:
        return 0
    agent_val = formula.agent.value if isinstance(formula.agent, DDICSymbol) else ""
    return inheritance.specificity_of(agent_val)  # type: ignore[union-attr]


def _any_modes_conflict(modes: set[object]) -> bool:
    mode_vals = {m.value if hasattr(m, "value") else str(m) for m in modes}
    return (
        {"obligatory", "forbidden"} <= mode_vals
        or {"optional", "forbidden"} <= mode_vals
    )


def _legacy_preemption(
    formulas: list[DDICFormula],
    spec_map: dict[str, int],
) -> tuple[list[DDICFormula], list[DDICFormula]]:
    defeated: set[int] = set()
    for i, a in enumerate(formulas):
        if i in defeated:
            continue
        for j, b in enumerate(formulas):
            if j <= i or j in defeated:
                continue
            if not _formula_modes_conflict(a, b):
                continue
            spec_a = spec_map.get(a.formula_id, 0)
            spec_b = spec_map.get(b.formula_id, 0)
            if spec_a > spec_b:
                defeated.add(j)
            elif spec_b > spec_a:
                defeated.add(i)
                break
    surviving = [f for i, f in enumerate(formulas) if i not in defeated]
    defeated_list = [f for i, f in enumerate(formulas) if i in defeated]
    return surviving, defeated_list


def _formula_modes_conflict(a: DDICFormula, b: DDICFormula) -> bool:
    if a.mode == b.mode:
        return False
    pair = {a.mode.value, b.mode.value}
    return pair == {"obligatory", "forbidden"} or pair == {"optional", "forbidden"}


def _legacy_resolve_by_prevalence(
    formulas: list[DDICFormula],
    code_map: dict[str, str],
    prevalence: tuple[str, ...],
) -> list[DDICFormula] | None:
    from aegis.engine.ddic_ir import DDICMode

    by_mode: dict[DDICMode, list[DDICFormula]] = {}
    for f in formulas:
        by_mode.setdefault(f.mode, []).append(f)
    if len(by_mode) < 2:
        return None

    best_mode: DDICMode | None = None
    best_rank = -1
    for mode, mode_formulas in by_mode.items():
        for f in mode_formulas:
            code = code_map.get(f.formula_id, "")
            if code in prevalence:
                rank = len(prevalence) - list(prevalence).index(code)
                if rank > best_rank:
                    best_rank = rank
                    best_mode = mode

    if best_mode is None:
        return None

    # Check for tie.
    for mode, mode_formulas in by_mode.items():
        if mode == best_mode:
            continue
        for f in mode_formulas:
            code = code_map.get(f.formula_id, "")
            if code in prevalence:
                rank = len(prevalence) - list(prevalence).index(code)
                if rank >= best_rank:
                    return None
    return by_mode[best_mode]


def _belief_state_from_winner(
    winner_mode: object,
    winners: list[DDICFormula],
    defeated: list[DDICFormula],
) -> DDICBeliefState:
    from aegis.engine.ddic_ir import DDICMode

    mode_val = winner_mode.value if isinstance(winner_mode, DDICMode) else str(winner_mode)
    if mode_val == "forbidden":
        verdict = DDICVerdict.FORBIDDEN
    elif mode_val in ("obligatory", "optional"):
        verdict = DDICVerdict.PERMITTED
    else:
        verdict = DDICVerdict.UNDECIDABLE

    return DDICBeliefState(
        active_beliefs=tuple(_asserted_formula(f) for f in winners),
        defeated_beliefs=tuple(_asserted_formula(f) for f in defeated),
        unresolved_conflicts=(),
        verdict=verdict,
    )


# ── Internal helpers ────────────────────────────────────────────────


def _asserted_formula(formula: DDICFormula) -> DerivedFormula:
    return DerivedFormula(
        formula=formula,
        derivation_id=formula.formula_id,
        origin=DerivationOrigin.ASSERTED,
        support=(formula.formula_id,),
        rule_id=None,
    )


def _apply_priority_defeat(
    runtime: DDICRuntime,
    priorities: tuple[DDICPriorityEdge, ...],
) -> None:
    priority_map = _priority_closure(priorities)
    if not priority_map:
        return

    defeated_ids: set[str] = set()
    by_derivation_id = {derived.derivation_id: derived for derived in runtime.active_formulas}

    for left in runtime.active_formulas:
        if left.origin != DerivationOrigin.DEFEASIBLE_RULE or left.rule_id is None:
            continue
        for right in runtime.active_formulas:
            if right.derivation_id == left.derivation_id:
                continue
            if right.origin != DerivationOrigin.DEFEASIBLE_RULE or right.rule_id is None:
                continue
            if not _beliefs_conflict(left.formula, right.formula):
                continue
            winner = _priority_winner(left, right, priority_map)
            if winner is None or winner.derivation_id != left.derivation_id:
                continue
            if right.derivation_id in defeated_ids:
                continue
            defeated_ids.add(right.derivation_id)
            runtime.defeats.append(
                DefeatEvent(
                    defeated_derivation_id=right.derivation_id,
                    defeating_formula_id=left.formula.formula_id,
                    defeating_rule_id=left.rule_id,
                    mode="complete",
                    reason=DefeatReason.PRIORITY,
                )
            )

    if not defeated_ids:
        return

    remaining: list[DerivedFormula] = []
    for derived in runtime.active_formulas:
        if derived.derivation_id in defeated_ids:
            runtime.defeated_formulas.append(by_derivation_id[derived.derivation_id])
            continue
        remaining.append(derived)
    runtime.active_formulas = remaining


def _apply_lex_posterior_defeat(
    runtime: DDICRuntime,
    relations: tuple[DDICRelation, ...],
    defeasible_rules: tuple[DDICDefeasibleRule, ...],
) -> None:
    by_id = {derived.formula.formula_id: derived for derived in runtime.inferred_formulas}
    rules_by_id = {rule.rule_id: rule for rule in defeasible_rules}
    remaining: list[DerivedFormula] = []
    for derived in runtime.active_formulas:
        if derived.origin != DerivationOrigin.DEFEASIBLE_RULE:
            remaining.append(derived)
            continue
        defeating = _find_later_inconsistent_testimony(derived, runtime.inferred_formulas, by_id, relations)
        if defeating is None:
            remaining.append(derived)
            continue
        defeating_formula = defeating
        defeat_mode = _defeat_mode_for(derived, rules_by_id)
        runtime.defeated_formulas.append(derived)
        runtime.defeats.append(
            DefeatEvent(
                defeated_derivation_id=derived.derivation_id,
                defeating_formula_id=defeating_formula.formula.formula_id,
                defeating_rule_id=None,
                mode=defeat_mode.value,
                reason=(
                    DefeatReason.SPECIFIC_EXCEPTION
                    if defeat_mode == DDICDefeatMode.PARTIAL
                    else DefeatReason.LEX_POSTERIOR
                ),
            )
        )
    runtime.active_formulas = remaining


def _find_later_inconsistent_testimony(
    derived: DerivedFormula,
    formulas: list[DerivedFormula],
    by_id: dict[str, DerivedFormula],
    relations: tuple[DDICRelation, ...],
) -> DerivedFormula | None:
    target = derived.formula
    if target.layer.value != "belief":
        return None
    if target.mode.value not in {"obligatory", "forbidden"}:
        return None
    expected_mode = "forbidden" if target.mode.value == "obligatory" else "obligatory"
    source_testimony_times = [
        support_formula.formula.time
        for support_id in derived.support
        if (support_formula := by_id.get(support_id)) is not None
        and support_formula.formula.layer.value == "testimony"
    ]
    if not source_testimony_times:
        return None

    for candidate in formulas:
        formula = candidate.formula
        if formula.layer.value != "testimony":
            continue
        if formula.mode.value != expected_mode:
            continue
        if formula.polarity.value != "positive":
            continue
        if formula.agent != target.agent:
            continue
        if not _overlaps(formula.behavior, target.behavior, relations, "behavior"):
            continue
        if not _overlaps(formula.context, target.context, relations, "context"):
            continue
        if any(_is_later(source_time, formula.time, relations) for source_time in source_testimony_times):
            return candidate
    return None


def _classify_conflicts(
    formulas: list[DerivedFormula],
    relations: tuple[DDICRelation, ...],
) -> list[ConflictEvent]:
    conflicts: list[ConflictEvent] = []
    asserted = [f for f in formulas if f.formula.layer.value == "testimony"]
    for i, left in enumerate(asserted):
        for right in asserted[i + 1 :]:
            if left.formula.agent != right.formula.agent:
                continue
            if not _modes_conflict(left.formula.mode.value, right.formula.mode.value):
                continue
            conflict = _classify_pair(left, right, relations)
            if conflict is not None:
                conflicts.append(conflict)
    return conflicts


def _classify_active_belief_conflicts(
    formulas: tuple[DerivedFormula, ...],
    relations: tuple[DDICRelation, ...],
) -> list[ConflictEvent]:
    conflicts: list[ConflictEvent] = []
    for i, left in enumerate(formulas):
        for right in formulas[i + 1 :]:
            if left.formula.agent != right.formula.agent:
                continue
            if left.formula.polarity != right.formula.polarity:
                continue
            if not _modes_conflict(left.formula.mode.value, right.formula.mode.value):
                continue
            conflict = _classify_pair(left, right, relations)
            if conflict is not None:
                conflicts.append(conflict)
    return conflicts


def _classify_pair(
    left: DerivedFormula,
    right: DerivedFormula,
    relations: tuple[DDICRelation, ...],
) -> ConflictEvent | None:
    if left.formula.context != right.formula.context and not _overlaps(
        left.formula.context, right.formula.context, relations, "context"
    ):
        return None

    if left.formula.behavior == right.formula.behavior:
        return ConflictEvent(
            left_formula_id=left.formula.formula_id,
            right_formula_id=right.formula.formula_id,
            conflict_type=ConflictType.DIRECT,
            shared_behavior=left.formula.behavior,
            shared_context=_shared_context(left.formula.context, right.formula.context, relations),
        )
    if _subsumes(left.formula.behavior, right.formula.behavior, relations, "behavior") or _subsumes(
        right.formula.behavior, left.formula.behavior, relations, "behavior"
    ):
        more_specific = (
            left.formula.behavior
            if _subsumes(left.formula.behavior, right.formula.behavior, relations, "behavior")
            else right.formula.behavior
        )
        return ConflictEvent(
            left_formula_id=left.formula.formula_id,
            right_formula_id=right.formula.formula_id,
            conflict_type=ConflictType.INDIRECT,
            shared_behavior=more_specific,
            shared_context=_shared_context(left.formula.context, right.formula.context, relations),
        )
    shared_behavior = _intersection(left.formula.behavior, right.formula.behavior, relations, "behavior")
    if shared_behavior is not None:
        return ConflictEvent(
            left_formula_id=left.formula.formula_id,
            right_formula_id=right.formula.formula_id,
            conflict_type=ConflictType.INTERSECTING,
            shared_behavior=shared_behavior,
            shared_context=_shared_context(left.formula.context, right.formula.context, relations),
        )
    return None


def _modes_conflict(left: str, right: str) -> bool:
    if left == right:
        return False
    pair = {left, right}
    return pair == {"obligatory", "forbidden"} or pair == {"optional", "forbidden"} or pair == {
        "permitted",
        "forbidden",
    }


def _beliefs_conflict(left: DDICFormula, right: DDICFormula) -> bool:
    if left.layer.value != "belief" or right.layer.value != "belief":
        return False
    if left.agent != right.agent:
        return False
    if left.polarity != right.polarity:
        return False
    if left.behavior != right.behavior:
        return False
    if left.context != right.context:
        return False
    if left.time != right.time:
        return False
    return _modes_conflict(left.mode.value, right.mode.value)


def _priority_winner(
    left: DerivedFormula,
    right: DerivedFormula,
    priorities: set[tuple[str, str]],
) -> DerivedFormula | None:
    left_rule = left.rule_id
    right_rule = right.rule_id
    if left_rule is None or right_rule is None:
        return None
    if (left_rule, right_rule) in priorities:
        return left
    if (right_rule, left_rule) in priorities:
        return right
    return None


def _priority_closure(priorities: tuple[DDICPriorityEdge, ...]) -> set[tuple[str, str]]:
    closure = {(edge.higher, edge.lower) for edge in priorities}
    if not closure:
        return closure
    changed = True
    while changed:
        changed = False
        additions: set[tuple[str, str]] = set()
        for higher, lower in closure:
            for candidate_higher, candidate_lower in closure:
                if lower == candidate_higher and (higher, candidate_lower) not in closure:
                    additions.add((higher, candidate_lower))
        if additions:
            closure.update(additions)
            changed = True
    return closure


def _verdict_from_active_beliefs(
    beliefs: tuple[DerivedFormula, ...],
    unresolved_conflicts: tuple[ConflictEvent, ...],
) -> DDICVerdict:
    if unresolved_conflicts:
        return DDICVerdict.UNDECIDABLE
    if any(
        belief.formula.mode.value == "forbidden" and belief.formula.polarity.value == "positive"
        for belief in beliefs
    ):
        return DDICVerdict.FORBIDDEN
    if any(
        belief.formula.mode.value in {"optional", "obligatory"} and belief.formula.polarity.value == "positive"
        for belief in beliefs
    ):
        return DDICVerdict.PERMITTED
    return DDICVerdict.UNDECIDABLE


def _defeat_mode_for(
    derived: DerivedFormula,
    defeasible_rules: dict[str, DDICDefeasibleRule],
) -> DDICDefeatMode:
    if derived.rule_id is None:
        return DDICDefeatMode.COMPLETE
    rule = defeasible_rules.get(derived.rule_id)
    if rule is None:
        return DDICDefeatMode.COMPLETE
    return rule.defeat_mode


def _is_later(earlier: object, later: object, relations: tuple[DDICRelation, ...]) -> bool:
    for relation in relations:
        if relation.kind == DDICRelationKind.BEFORE and relation.args == (earlier, later):
            return True
    return False


def _overlaps(a: object, b: object, relations: tuple[DDICRelation, ...], namespace: str) -> bool:
    return (
        a == b
        or _is_top(a)
        or _is_top(b)
        or _subsumes(a, b, relations, namespace)
        or _subsumes(b, a, relations, namespace)
        or _intersection(a, b, relations, namespace) is not None
    )


def _shared_context(a: object, b: object, relations: tuple[DDICRelation, ...]) -> object | None:
    if a == b:
        return a
    if _is_top(a):
        return b
    if _is_top(b):
        return a
    if _subsumes(a, b, relations, "context"):
        return a
    if _subsumes(b, a, relations, "context"):
        return b
    return _intersection(a, b, relations, "context")


def _subsumes(sub: object, sup: object, relations: tuple[DDICRelation, ...], namespace: str) -> bool:
    if sub == sup:
        return True
    kind = (
        DDICRelationKind.BEHAVIOR_SUBSUMES
        if namespace == "behavior"
        else DDICRelationKind.CONTEXT_SUBSUMES
    )
    for relation in relations:
        if relation.kind == kind and relation.args == (sub, sup):
            return True
    return False


def _intersection(a: object, b: object, relations: tuple[DDICRelation, ...], namespace: str) -> object | None:
    kind = (
        DDICRelationKind.BEHAVIOR_INTERSECTS
        if namespace == "behavior"
        else DDICRelationKind.CONTEXT_INTERSECTS
    )
    for relation in relations:
        if relation.kind != kind:
            continue
        if relation.args[0] == a and relation.args[1] == b:
            return relation.args[2]
        if relation.args[0] == b and relation.args[1] == a:
            return relation.args[2]
    return None


def _is_top(value: object) -> bool:
    return isinstance(value, DDICSymbol) and value.value == "Top"


def _apply_defeasible_rule(
    rule: DDICDefeasibleRule,
    formulas: tuple[DerivedFormula, ...],
    relations: tuple[DDICRelation, ...],
) -> list[Bindings]:
    initial = _bindings_for_rule_head(rule.antecedent, formulas)
    results: list[Bindings] = []
    for binding in initial:
        enriched = _satisfy_conditions(rule.guards, binding, formulas, relations)
        results.extend(enriched)
    return results


def _apply_rule_body(
    body: tuple[DDICCondition, ...],
    formulas: tuple[DerivedFormula, ...],
    relations: tuple[DDICRelation, ...],
) -> list[Bindings]:
    return _satisfy_conditions(body, {"_support": []}, formulas, relations)


def _satisfy_conditions(
    conditions: tuple[DDICCondition, ...],
    binding: Bindings,
    formulas: tuple[DerivedFormula, ...],
    relations: tuple[DDICRelation, ...],
) -> list[Bindings]:
    results = [binding]
    for condition in conditions:
        next_results: list[Bindings] = []
        for current in results:
            next_results.extend(_satisfy_condition(condition, current, formulas, relations))
        results = next_results
        if not results:
            break
    return results


def _satisfy_condition(
    condition: DDICCondition,
    binding: Bindings,
    formulas: tuple[DerivedFormula, ...],
    relations: tuple[DDICRelation, ...],
) -> list[Bindings]:
    if isinstance(condition, FormulaCondition):
        return _match_formula_condition(condition.formula, binding, formulas)
    if isinstance(condition, RelationCondition):
        return _match_relation_condition(condition, binding, relations)
    if isinstance(condition, PredicateCondition):
        return []
    return []


def _bindings_for_rule_head(
    head: DDICFormulaPattern | PredicateCondition,
    formulas: tuple[DerivedFormula, ...],
) -> list[Bindings]:
    if isinstance(head, DDICFormulaPattern):
        return _match_formula_condition(head, {"_support": []}, formulas)
    return []


def _match_formula_condition(
    pattern: DDICFormulaPattern,
    binding: Bindings,
    formulas: tuple[DerivedFormula, ...],
) -> list[Bindings]:
    matches: list[Bindings] = []
    for derived in formulas:
        formula = derived.formula
        if formula.layer.value != pattern.layer.value:
            continue
        if formula.mode.value != pattern.mode.value:
            continue
        if formula.polarity.value != pattern.polarity.value:
            continue
        current = dict(binding)
        if not _bind_pattern_term(pattern.agent, formula.agent, current):
            continue
        if not _bind_pattern_term(pattern.behavior, formula.behavior, current):
            continue
        if not _bind_pattern_term(pattern.context, formula.context, current):
            continue
        if not _bind_pattern_term(pattern.time, formula.time, current):
            continue
        support = list(current.get("_support", []))
        support.append(derived.formula.formula_id)
        current["_support"] = support
        matches.append(current)
    return matches


def _match_relation_condition(
    condition: RelationCondition,
    binding: Bindings,
    relations: tuple[DDICRelation, ...],
) -> list[Bindings]:
    matches: list[Bindings] = []
    for relation in relations:
        if relation.kind != condition.kind:
            continue
        if len(relation.args) != len(condition.args):
            continue
        current = dict(binding)
        ok = True
        for pattern_arg, actual_arg in zip(condition.args, relation.args, strict=True):
            if not _bind_pattern_term(pattern_arg, actual_arg, current):
                ok = False
                break
        if ok:
            matches.append(current)
    return matches


def _instantiate_rule_head(
    head: DDICFormulaPattern | PredicateCondition,
    binding: Bindings,
    rule_id: str,
    source_ref: str,
) -> DDICFormula:
    if isinstance(head, DDICFormulaPattern):
        return _instantiate_formula_pattern(head, binding, source_ref=source_ref, formula_id=rule_id)
    raise ValueError(f"Unsupported rule head for instantiation: {head!r}")


def _instantiate_formula_pattern(
    pattern: DDICFormulaPattern,
    binding: Bindings,
    *,
    source_ref: str,
    formula_id: str,
) -> DDICFormula:
    return DDICFormula(
        formula_id=formula_id,
        layer=pattern.layer,
        mode=pattern.mode,
        polarity=pattern.polarity,
        agent=_resolve_pattern_term(pattern.agent, binding),
        behavior=_resolve_pattern_term(pattern.behavior, binding),
        context=_resolve_pattern_term(pattern.context, binding),
        time=_resolve_pattern_term(pattern.time, binding),
        source_ref=source_ref,
    )


def _resolve_pattern_term(term: DDICPatternTerm, binding: Bindings) -> object:
    if isinstance(term, DDICVar):
        return binding[term.name]
    return term


def _bind_pattern_term(pattern: DDICPatternTerm, actual: object, binding: Bindings) -> bool:
    if isinstance(pattern, DDICVar):
        existing = binding.get(pattern.name)
        if existing is None:
            binding[pattern.name] = actual
            return True
        return existing == actual
    return pattern == actual
