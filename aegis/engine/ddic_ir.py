"""DDIC intermediate representation and AST -> IR compilation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias

from aegis.deontic import ddic_ast


class DDICLayer(Enum):
    TESTIMONY = "testimony"
    BELIEF = "belief"


class DDICMode(Enum):
    OBLIGATORY = "obligatory"
    FORBIDDEN = "forbidden"
    OPTIONAL = "optional"


class DDICPolarity(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass(frozen=True, slots=True)
class DDICSymbol:
    value: str


@dataclass(frozen=True, slots=True)
class DDICInteger:
    value: int


@dataclass(frozen=True, slots=True)
class DDICVar:
    name: str


type DDICTerm = DDICSymbol | DDICInteger | DDICCompound
type DDICPatternTerm = DDICVar | DDICTerm


@dataclass(frozen=True, slots=True)
class DDICCompound:
    head: str
    args: tuple[DDICTerm, ...]


@dataclass(frozen=True, slots=True)
class DDICFormula:
    formula_id: str
    layer: DDICLayer
    mode: DDICMode
    polarity: DDICPolarity
    agent: DDICTerm
    behavior: DDICTerm
    context: DDICTerm
    time: DDICTerm
    source_ref: str


@dataclass(frozen=True, slots=True)
class DDICFormulaPattern:
    layer: DDICLayer
    mode: DDICMode
    polarity: DDICPolarity
    agent: DDICPatternTerm
    behavior: DDICPatternTerm
    context: DDICPatternTerm
    time: DDICPatternTerm


class DDICRelationKind(Enum):
    ISA = "isa"
    BEFORE = "before"
    BEFORE_OR_EQUAL = "before-or-equal"
    BETWEEN_INCLUSIVE = "between-inclusive"
    BEHAVIOR_SUBSUMES = "behavior-subsumes"
    CONTEXT_SUBSUMES = "context-subsumes"
    BEHAVIOR_INTERSECTS = "behavior-intersects"
    CONTEXT_INTERSECTS = "context-intersects"


@dataclass(frozen=True, slots=True)
class DDICRelation:
    relation_id: str
    kind: DDICRelationKind
    args: tuple[DDICTerm, ...]
    source_ref: str


class DDICCondition:
    """Marker base class for DDIC rule conditions."""


@dataclass(frozen=True, slots=True)
class FormulaCondition(DDICCondition):
    formula: DDICFormulaPattern


@dataclass(frozen=True, slots=True)
class RelationCondition(DDICCondition):
    kind: DDICRelationKind
    args: tuple[DDICPatternTerm, ...]


@dataclass(frozen=True, slots=True)
class PredicateCondition(DDICCondition):
    predicate: str
    args: tuple[DDICPatternTerm, ...]


DDICRuleHead: TypeAlias = DDICFormulaPattern | PredicateCondition


@dataclass(frozen=True, slots=True)
class DDICDefaultRule:
    rule_id: str
    head: DDICRuleHead
    body: tuple[DDICCondition, ...]
    source_ref: str


class DDICDefeatMode(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class DDICDefeasibleRule:
    rule_id: str
    antecedent: DDICFormulaPattern | PredicateCondition
    consequent: DDICFormulaPattern | PredicateCondition
    guards: tuple[DDICCondition, ...]
    justification_schema: tuple[DDICCondition, ...]
    defeat_mode: DDICDefeatMode
    source_ref: str


@dataclass(frozen=True, slots=True)
class DDICPriorityEdge:
    higher: str
    lower: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class DDICMetadata:
    key: str
    value: DDICTerm
    source_ref: str


class PlanConstraintKind(Enum):
    """The four canonical plan-level constraints (AEGIS-2703, Epic 27).

    Kebab-case values match the established DDIC-IR naming convention
    so MELD-side authoring uses the same vocabulary as the
    intermediate representation.
    """

    OBLIGATE_SEQUENCE = "obligate-sequence"
    """Step A must precede step B (typed-action ordering)."""

    FORBID_AGGREGATE = "forbid-aggregate"
    """At most N occurrences of action-type X within the plan."""

    OBLIGATE_WITHIN = "obligate-within"
    """Step A must occur within T seconds of step B
    (uses ``PlanStep.scheduled_duration_s``, not wall-clock)."""

    REQUIRE_PRECONDITION = "require-precondition"
    """Step A's pre-state must satisfy condition P."""


@dataclass(frozen=True, slots=True)
class DDICPlanConstraint:
    """One declared plan-level constraint carried by DDICModule.

    The historical name marks the shared IR container, not a DDIC
    inference rule. DDIC resolves conflicts between deontic action
    norms; the plan evaluator consumes these constraints as a separate
    Guard-side composition layer for whole-plan verdicts.
    """

    constraint_id: str
    kind: PlanConstraintKind
    args: tuple[DDICTerm, ...] = ()
    layer: DDICLayer = DDICLayer.BELIEF
    mode: DDICMode = DDICMode.OBLIGATORY
    polarity: DDICPolarity = DDICPolarity.POSITIVE
    source_ref: str = ""
    agent_pattern: DDICTerm = field(default_factory=lambda: DDICSymbol("*"))
    specificity: int = 0
    defeasible: bool = True


@dataclass(frozen=True, slots=True)
class DDICModule:
    formulas: tuple[DDICFormula, ...]
    relations: tuple[DDICRelation, ...]
    defaults: tuple[DDICDefaultRule, ...]
    defeasible_rules: tuple[DDICDefeasibleRule, ...]
    priorities: tuple[DDICPriorityEdge, ...]
    metadata: tuple[DDICMetadata, ...] = ()
    resolution_strategy: str = "ddic"  # "legacy" (v1 6-step) | "ddic" (v2 priority/defeat)
    code_prevalence: tuple[str, ...] = ()  # code ordering for legacy strategy
    # Plan-level extension (AEGIS-2703, Epic 27). Defaults make the
    # field backward-compatible — existing modules carry no plan
    # constraints and the obligation-coverage flag is opt-in (off by
    # default), tracking Olson's open question on
    # Obligation→Intention.
    plan_constraints: tuple[DDICPlanConstraint, ...] = ()
    require_obligation_coverage: bool = False


def compile_meld_module(module: ddic_ast.MeldModule) -> DDICModule:
    """Compile a parsed MELD v2-DDIC module into DDIC IR."""
    formulas: list[DDICFormula] = []
    relations: list[DDICRelation] = []
    defaults: list[DDICDefaultRule] = []
    defeasible_rules: list[DDICDefeasibleRule] = []
    priorities: list[DDICPriorityEdge] = []
    metadata: list[DDICMetadata] = []
    plan_constraints: list[DDICPlanConstraint] = []

    for statement in module.statements:
        if isinstance(statement, ddic_ast.NormativeFormulaStatement):
            formulas.append(_compile_formula_statement(statement))
        elif isinstance(statement, ddic_ast.RelationStatement):
            relations.append(_compile_relation_statement(statement))
        elif isinstance(statement, ddic_ast.DefaultRuleStatement):
            defaults.append(_compile_default_rule(statement))
        elif isinstance(statement, ddic_ast.DefeasibleRuleStatement):
            defeasible_rules.append(_compile_defeasible_rule(statement))
        elif isinstance(statement, ddic_ast.PriorityStatement):
            priorities.append(
                DDICPriorityEdge(
                    higher=statement.higher,
                    lower=statement.lower,
                    source_ref=_source_ref(statement.span),
                )
            )
        elif isinstance(statement, ddic_ast.NormIdStatement):
            metadata.append(
                DDICMetadata(
                    key="norm-id",
                    value=_compile_pattern_term(statement.target),
                    source_ref=_source_ref(statement.span),
                )
            )
        elif isinstance(statement, ddic_ast.SourceIdStatement):
            metadata.append(
                DDICMetadata(
                    key="source-id",
                    value=DDICSymbol(statement.source_id),
                    source_ref=_source_ref(statement.span),
                )
            )
        elif isinstance(statement, ddic_ast.PlanConstraintStatement):
            plan_constraints.append(
                _compile_plan_constraint_statement(
                    statement, len(plan_constraints)
                )
            )

    return DDICModule(
        formulas=tuple(formulas),
        relations=tuple(relations),
        defaults=tuple(defaults),
        defeasible_rules=tuple(defeasible_rules),
        priorities=tuple(priorities),
        metadata=tuple(metadata),
        plan_constraints=tuple(plan_constraints),
    )


def _compile_formula_statement(statement: ddic_ast.NormativeFormulaStatement) -> DDICFormula:
    formula = statement.formula
    return DDICFormula(
        formula_id=f"{statement.span.file}:{statement.span.line}",
        layer=DDICLayer(formula.layer.value),
        mode=DDICMode(formula.mode.value),
        polarity=DDICPolarity(formula.polarity.value),
        agent=_compile_term(formula.agent),
        behavior=_compile_term(formula.behavior),
        context=_compile_term(formula.context),
        time=_compile_term(formula.time),
        source_ref=_source_ref(statement.span),
    )


# AEGIS-2706 (Epic 27): map the v2 AST kebab-case enum to the IR
# kebab-case enum. The two enums share string values for parity.
_AST_KIND_TO_IR_KIND: dict[ddic_ast.PlanConstraintKindAst, PlanConstraintKind] = {
    ddic_ast.PlanConstraintKindAst.OBLIGATE_SEQUENCE: (
        PlanConstraintKind.OBLIGATE_SEQUENCE
    ),
    ddic_ast.PlanConstraintKindAst.FORBID_AGGREGATE: (
        PlanConstraintKind.FORBID_AGGREGATE
    ),
    ddic_ast.PlanConstraintKindAst.OBLIGATE_WITHIN: (
        PlanConstraintKind.OBLIGATE_WITHIN
    ),
    ddic_ast.PlanConstraintKindAst.REQUIRE_PRECONDITION: (
        PlanConstraintKind.REQUIRE_PRECONDITION
    ),
}

# Per-kind IR layer + mode (Olson reading): preconditions are belief
# queries, the others are testimony obligations / forbids. Polarity
# is always POSITIVE; negation is expressed via mode.
_IR_KIND_PROFILE: dict[
    PlanConstraintKind, tuple[DDICLayer, DDICMode, DDICPolarity]
] = {
    PlanConstraintKind.OBLIGATE_SEQUENCE: (
        DDICLayer.TESTIMONY,
        DDICMode.OBLIGATORY,
        DDICPolarity.POSITIVE,
    ),
    PlanConstraintKind.FORBID_AGGREGATE: (
        DDICLayer.TESTIMONY,
        DDICMode.FORBIDDEN,
        DDICPolarity.POSITIVE,
    ),
    PlanConstraintKind.OBLIGATE_WITHIN: (
        DDICLayer.TESTIMONY,
        DDICMode.OBLIGATORY,
        DDICPolarity.POSITIVE,
    ),
    PlanConstraintKind.REQUIRE_PRECONDITION: (
        DDICLayer.BELIEF,
        DDICMode.OBLIGATORY,
        DDICPolarity.POSITIVE,
    ),
}


def _compile_plan_constraint_statement(
    statement: ddic_ast.PlanConstraintStatement,
    index: int,
) -> DDICPlanConstraint:
    """Compile a v2 PlanConstraintStatement to a DDICPlanConstraint.

    AEGIS-2706 acceptance: kebab-case IR values, byte-identical to the
    v1 path so a v1 file and a v2 file with the same plan-constraints
    produce structurally equal ``DDICPlanConstraint`` tuples (the
    1:1 cross-version parity test in ``test_meld_v2_plan_constraints``
    locks this in).

    The compile step does NOT validate per-kind argument shapes —
    that is the verification pipeline's job (AEGIS-2707). Args are
    term-compiled as-is; ill-typed args (e.g. a string where an int
    is expected by ``forbid-aggregate``) survive into the IR and
    will be rejected by the verifier with a single informative
    diagnostic referencing ``source_ref``.
    """
    ir_kind = _AST_KIND_TO_IR_KIND[statement.kind]
    layer, mode, polarity = _IR_KIND_PROFILE[ir_kind]
    return DDICPlanConstraint(
        constraint_id=f"plan-{statement.kind.value}:{index}",
        kind=ir_kind,
        args=tuple(_compile_term(arg) for arg in statement.args),
        layer=layer,
        mode=mode,
        polarity=polarity,
        source_ref=_source_ref(statement.span),
    )


def _compile_relation_statement(statement: ddic_ast.RelationStatement) -> DDICRelation:
    return DDICRelation(
        relation_id=f"{statement.span.file}:{statement.span.line}",
        kind=DDICRelationKind(statement.kind.value),
        args=tuple(_compile_term(arg) for arg in statement.args),
        source_ref=_source_ref(statement.span),
    )


def _compile_default_rule(statement: ddic_ast.DefaultRuleStatement) -> DDICDefaultRule:
    return DDICDefaultRule(
        rule_id=statement.rule_id,
        head=_compile_rule_head(statement.head),
        body=tuple(_compile_condition(item) for item in statement.body),
        source_ref=_source_ref(statement.span),
    )


def _compile_defeasible_rule(statement: ddic_ast.DefeasibleRuleStatement) -> DDICDefeasibleRule:
    return DDICDefeasibleRule(
        rule_id=statement.rule_id,
        antecedent=_compile_rule_head(statement.from_formula),
        consequent=_compile_rule_head(statement.to_formula),
        guards=tuple(_compile_condition(item) for item in statement.when_conditions),
        justification_schema=tuple(
            _compile_condition(item) for item in statement.justification_conditions
        ),
        defeat_mode=DDICDefeatMode(statement.defeat_mode.value if statement.defeat_mode else "complete"),
        source_ref=_source_ref(statement.span),
    )


def _compile_rule_head(value: object) -> DDICRuleHead:
    if isinstance(value, tuple) and value:
        head = value[0]
        if isinstance(head, str) and head in _FORMULA_PREDICATES:
            return _compile_formula_pattern(value)
    if isinstance(value, tuple) and value:
        pred = value[0]
        if isinstance(pred, str):
            return PredicateCondition(
                predicate=pred,
                args=tuple(_compile_pattern_term(arg) for arg in value[1:]),
            )
    raise ValueError(f"Unsupported rule head: {value!r}")


def _compile_condition(value: object) -> DDICCondition:
    if isinstance(value, tuple) and value:
        head = value[0]
        if isinstance(head, str) and head in _FORMULA_PREDICATES:
            return FormulaCondition(formula=_compile_formula_pattern(value))
        if isinstance(head, str) and head in _RELATION_PREDICATES:
            return RelationCondition(
                kind=DDICRelationKind(_RELATION_PREDICATES[head]),
                args=tuple(_compile_pattern_term(arg) for arg in value[1:]),
            )
        if isinstance(head, str):
            return PredicateCondition(
                predicate=head,
                args=tuple(_compile_pattern_term(arg) for arg in value[1:]),
            )
    raise ValueError(f"Unsupported condition: {value!r}")


def _compile_formula_pattern(value: tuple[object, ...]) -> DDICFormulaPattern:
    pred = str(value[0])
    layer, polarity, mode = _FORMULA_PREDICATES[pred]
    return DDICFormulaPattern(
        layer=DDICLayer(layer),
        mode=DDICMode(mode),
        polarity=DDICPolarity(polarity),
        agent=_compile_pattern_term(value[1]),
        behavior=_compile_pattern_term(value[2]),
        context=_compile_pattern_term(value[3]),
        time=_compile_pattern_term(value[4]),
    )


def _compile_pattern_term(value: object) -> DDICPatternTerm:
    if isinstance(value, str) and value.startswith("?"):
        return DDICVar(name=value)
    return _compile_term(value)


def _compile_term(value: object) -> DDICTerm:
    if isinstance(value, int):
        return DDICInteger(value)
    if isinstance(value, str):
        return DDICSymbol(value)
    if isinstance(value, tuple) and value:
        head = value[0]
        if not isinstance(head, str):
            raise ValueError(f"Compound head must be a string: {value!r}")
        return DDICCompound(head=head, args=tuple(_compile_term(arg) for arg in value[1:]))
    raise ValueError(f"Unsupported term: {value!r}")


def _source_ref(span: ddic_ast.SourceSpan) -> str:
    return f"{span.file}:{span.line}"


_FORMULA_PREDICATES: dict[str, tuple[str, str, str]] = {
    "testimony-obligatory": ("testimony", "positive", "obligatory"),
    "testimony-forbidden": ("testimony", "positive", "forbidden"),
    "testimony-optional": ("testimony", "positive", "optional"),
    "belief-obligatory": ("belief", "positive", "obligatory"),
    "belief-forbidden": ("belief", "positive", "forbidden"),
    "belief-optional": ("belief", "positive", "optional"),
    "not-testimony-obligatory": ("testimony", "negative", "obligatory"),
    "not-testimony-forbidden": ("testimony", "negative", "forbidden"),
    "not-belief-obligatory": ("belief", "negative", "obligatory"),
    "not-belief-forbidden": ("belief", "negative", "forbidden"),
}

_RELATION_PREDICATES: dict[str, str] = {
    "isa": "isa",
    "before": "before",
    "before-or-equal": "before-or-equal",
    "between-inclusive": "between-inclusive",
    "behavior-subsumes": "behavior-subsumes",
    "context-subsumes": "context-subsumes",
    "behavior-intersects": "behavior-intersects",
    "context-intersects": "context-intersects",
}
