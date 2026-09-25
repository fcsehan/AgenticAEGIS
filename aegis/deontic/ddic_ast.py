"""AST model for MELD v2-DDIC.

This module implements the initial typed AST required by AEGIS-2302.
It is intentionally minimal and only covers the constructs currently
specified by the v2 parser tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Source location of a parsed AST node."""

    file: str
    line: int


Term: TypeAlias = str | int | tuple[object, ...]


@dataclass(frozen=True, slots=True)
class CompoundTerm:
    """Generic compound MELD term."""

    head: str
    args: tuple[Term, ...]
    span: SourceSpan


class FormulaPolarity(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class DeonticMode(Enum):
    OBLIGATORY = "obligatory"
    FORBIDDEN = "forbidden"
    OPTIONAL = "optional"


class NormativeLayer(Enum):
    TESTIMONY = "testimony"
    BELIEF = "belief"


@dataclass(frozen=True, slots=True)
class MeldModule:
    schema_version: int
    statements: tuple[object, ...]
    source_path: str = ""


@dataclass(frozen=True, slots=True)
class CaseStatement:
    mt_name: str
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class NormativeFormula:
    layer: NormativeLayer
    polarity: FormulaPolarity
    mode: DeonticMode
    agent: Term
    behavior: Term
    context: Term
    time: Term
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class NormativeFormulaStatement:
    formula: NormativeFormula
    span: SourceSpan


class RelationKind(Enum):
    ISA = "isa"
    BEFORE = "before"
    BEFORE_OR_EQUAL = "before-or-equal"
    BETWEEN_INCLUSIVE = "between-inclusive"
    BEHAVIOR_SUBSUMES = "behavior-subsumes"
    CONTEXT_SUBSUMES = "context-subsumes"
    BEHAVIOR_INTERSECTS = "behavior-intersects"
    CONTEXT_INTERSECTS = "context-intersects"


@dataclass(frozen=True, slots=True)
class RelationStatement:
    kind: RelationKind
    args: tuple[Term, ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class FactStatement:
    predicate: str
    args: tuple[Term, ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class DefaultRuleStatement:
    rule_id: str
    head: Term
    body: tuple[Term, ...]
    raw_form: CompoundTerm
    span: SourceSpan


class DefeatMode(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class DefeasibleRuleStatement:
    rule_id: str
    from_formula: Term
    to_formula: Term
    when_conditions: tuple[Term, ...]
    justification_conditions: tuple[Term, ...]
    defeat_mode: DefeatMode | None
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class PriorityStatement:
    higher: str
    lower: str
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class NormIdStatement:
    norm_id: str
    target: Term
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class SourceIdStatement:
    target_id: str
    source_id: str
    span: SourceSpan


# ── Plan-Constraints (AEGIS-2706, Epic 27) ─────────────────────────


class PlanConstraintKindAst(Enum):
    """v2-AST kind for plan-level constraints.

    The values are kebab-case to match the v2 surface form. The IR
    layer (``aegis.engine.ddic_ir.PlanConstraintKind``) shares the
    same string values for round-trip parity.
    """

    OBLIGATE_SEQUENCE = "obligate-sequence"
    FORBID_AGGREGATE = "forbid-aggregate"
    OBLIGATE_WITHIN = "obligate-within"
    REQUIRE_PRECONDITION = "require-precondition"


@dataclass(frozen=True, slots=True)
class PlanConstraintStatement:
    """A plan-level constraint declared in MELD v2-DDIC.

    Carries the parsed kind plus the raw argument tuple. Per-kind
    semantic validation (e.g. ``forbid-aggregate`` requires an integer
    threshold) happens at IR-compile time so the verification pipeline
    in AEGIS-2707 can emit one diagnostic per file rather than failing
    the parse on the first issue.
    """

    kind: PlanConstraintKindAst
    args: tuple[Term, ...]
    span: SourceSpan
