"""MELD Loader — S-expression parser for .meld files.

MELD = Modal Ethics Logic Definitions.
Parses the AEGIS MELD format (34 symbols, historically derived from CycL).
Converts deontic assertions to NormFrames.  Handles ``(case Mt)`` switching.
Error handling per D-004: syntax errors → MeldSyntaxError with file + line.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aegis.deontic import ddic_ast
from aegis.deontic.modality import DEONTIC_PREDICATES, DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.deontic.plan_norm_frame import PlanNormFrame

if TYPE_CHECKING:
    from aegis.kb.knowledge_base import KnowledgeBase
from aegis.errors import MeldSyntaxError

logger = logging.getLogger(__name__)

# Expected arities for deontic predicates.
_DEONTIC_ARITY: dict[str, int] = {
    "oughtToDo": 2,
    "forbiddenToDo": 2,
    "permittedToDo": 2,
    "oughtToDo-WRT": 3,
    "forbiddenToDo-WRT": 3,
    "permittedToDo-WRT": 3,
    "oughtToBe": 1,
    "forbiddenToBe": 1,
    "permittedToBe": 1,
}


# ── Plan-Constraint Predicates (AEGIS-2704, Epic 27) ────────────────

PLAN_CONSTRAINT_PREDICATES: frozenset[str] = frozenset(
    {
        "obligateSequence",
        "forbidAggregate",
        "obligateWithin",
        "requirePrecondition",
    }
)

# All four plan-constraint predicates take exactly two arguments in
# the v1 surface form. v2 may add an explicit ``:agent`` slot.
_PLAN_CONSTRAINT_ARITY: dict[str, int] = {
    "obligateSequence": 2,
    "forbidAggregate": 2,
    "obligateWithin": 2,
    "requirePrecondition": 2,
}

# Allowed symbolic timeframes for ``obligateWithin``. Anything else
# must be a non-negative integer (interpreted as cumulative seconds).
_VALID_TIMEFRAME_SYMBOLS: frozenset[str] = frozenset(
    {"immediate", "same-session", "end-of-plan"}
)


# ── S-Expression Tokenizer ──────────────────────────────────────────


def _tokenize(text: str, file: str = "<string>") -> list[tuple[str, int]]:
    """Tokenize *text* into (token, line_number) pairs.

    Tokens are: ``(``, ``)``, quoted strings, or atoms.
    """
    tokens: list[tuple[str, int]] = []
    i = 0
    line = 1
    n = len(text)

    while i < n:
        ch = text[i]

        # Whitespace
        if ch in " \t\r":
            i += 1
            continue
        if ch == "\n":
            line += 1
            i += 1
            continue

        # Line comment (;; to end of line)
        if ch == ";":
            while i < n and text[i] != "\n":
                i += 1
            continue

        # Parentheses
        if ch == "(":
            tokens.append(("(", line))
            i += 1
            continue
        if ch == ")":
            tokens.append((")", line))
            i += 1
            continue

        # String literal (may span multiple lines per grammar §2 Besonderheiten)
        if ch == '"':
            start_line = line
            i += 1
            parts: list[str] = []
            while i < n:
                if text[i] == "\\":
                    if i + 1 < n and text[i + 1] == '"':
                        parts.append('"')
                        i += 2
                        continue
                    parts.append(text[i])
                    i += 1
                    continue
                if text[i] == '"':
                    i += 1
                    break
                if text[i] == "\n":
                    line += 1
                parts.append(text[i])
                i += 1
            else:
                raise MeldSyntaxError(file, start_line, "Unterminated string literal")
            tokens.append(('"' + "".join(parts) + '"', start_line))
            continue

        # Atom (symbol, integer, identifier with dashes/underscores)
        start = i
        start_line = line
        while i < n and text[i] not in ' \t\r\n()"':
            i += 1
        tokens.append((text[start:i], start_line))

    return tokens


# ── S-Expression Parser ─────────────────────────────────────────────


def _parse_sexpr(tokens: list[tuple[str, int]], pos: int, file: str) -> tuple[Any, int]:
    """Parse one S-expression starting at *pos*. Returns (expr, new_pos)."""
    if pos >= len(tokens):
        raise MeldSyntaxError(file, 0, "Unexpected end of input")

    tok, line = tokens[pos]

    if tok == "(":
        pos += 1
        elements: list[Any] = []
        depth = 0
        while pos < len(tokens):
            if tokens[pos][0] == ")":
                pos += 1
                if not elements:
                    raise MeldSyntaxError(file, line, "Empty assertion ()")
                return tuple(elements), pos
            element, pos = _parse_sexpr(tokens, pos, file)
            elements.append(element)
            depth += 1
            if depth > 1000:
                raise MeldSyntaxError(file, line, "Nesting depth exceeds limit (D-007)")
        raise MeldSyntaxError(file, line, "Unclosed parenthesis")

    if tok == ")":
        raise MeldSyntaxError(file, line, "Unexpected ')'")

    # String literal
    if tok.startswith('"') and tok.endswith('"'):
        return tok[1:-1], pos + 1

    # Integer literal
    try:
        return int(tok), pos + 1
    except ValueError:
        pass

    # Symbol (atom)
    return tok, pos + 1


def parse_meld(text: str, file: str = "<string>") -> list[tuple[Any, ...]]:
    """Parse a .meld file into a list of S-expression tuples.

    Each top-level ``(predicate args...)`` becomes a tuple.
    """
    return [expr for expr, _line in _parse_meld_with_lines(text, file)]


def _parse_meld_with_lines(text: str, file: str = "<string>") -> list[tuple[tuple[Any, ...], int]]:
    """Parse a .meld file into S-expressions and assertion-order line numbers.

    The line number is intentionally the top-level assertion ordinal, which
    matches the existing loader's provenance semantics.
    """
    tokens = _tokenize(text, file)
    assertions: list[tuple[tuple[Any, ...], int]] = []
    pos = 0
    assertion_line = 0

    while pos < len(tokens):
        tok, line = tokens[pos]
        if tok == ")":
            raise MeldSyntaxError(file, line, "Unexpected ')' at top level")
        if tok == "(":
            expr, pos = _parse_sexpr(tokens, pos, file)
            if isinstance(expr, tuple):
                assertion_line += 1
                assertions.append((expr, assertion_line))
            else:
                raise MeldSyntaxError(file, line, "Top-level expression must be a list")
        else:
            raise MeldSyntaxError(file, line, f"Unexpected token at top level: {tok!r}")

    return assertions


def parse_meld_module(text: str, file: str = "<string>") -> ddic_ast.MeldModule:
    """Parse a MELD v2-DDIC module into a typed AST.

    Version 1 files are accepted for compatibility but v2-only constructs are
    rejected unless ``aegis-schema-version 2`` is active.
    """
    assertions = _parse_meld_with_lines(text, file)
    schema_version: int | None = None
    statements: list[object] = []
    current_mt: str | None = None

    for assertion, line in assertions:
        predicate = assertion[0] if assertion else None
        span = ddic_ast.SourceSpan(file=file, line=line)

        if predicate == "aegis-schema-version":
            if len(assertion) != 2:
                raise MeldSyntaxError(file, line, "aegis-schema-version expects exactly 1 argument")
            version = assertion[1]
            if not isinstance(version, int) or version < 1:
                raise MeldSyntaxError(file, line, f"Unknown schema version: {version}")
            if version > 2:
                raise MeldSyntaxError(
                    file, line, f"Unknown schema version: {version} (supported: 1, 2)"
                )
            schema_version = version
            continue

        if predicate == "case":
            if len(assertion) != 2:
                raise MeldSyntaxError(file, line, "case expects exactly 1 argument")
            current_mt = str(assertion[1])
            statements.append(ddic_ast.CaseStatement(mt_name=current_mt, span=span))
            continue

        if current_mt is None:
            raise MeldSyntaxError(file, line, "No microtheory declared (missing 'case')")

        version = schema_version or 1
        if version != 2 and isinstance(predicate, str) and predicate in _DDIC_ONLY_PREDICATES:
            raise MeldSyntaxError(file, line, f"{predicate} requires aegis-schema-version 2")

        statements.append(_ast_statement_from_assertion(assertion, span))

    return ddic_ast.MeldModule(
        schema_version=schema_version or 1,
        statements=tuple(statements),
        source_path=file,
    )


_NORMATIVE_PREDICATES: dict[
    str, tuple[ddic_ast.NormativeLayer, ddic_ast.FormulaPolarity, ddic_ast.DeonticMode]
] = {
    "testimony-obligatory": (
        ddic_ast.NormativeLayer.TESTIMONY,
        ddic_ast.FormulaPolarity.POSITIVE,
        ddic_ast.DeonticMode.OBLIGATORY,
    ),
    "testimony-forbidden": (
        ddic_ast.NormativeLayer.TESTIMONY,
        ddic_ast.FormulaPolarity.POSITIVE,
        ddic_ast.DeonticMode.FORBIDDEN,
    ),
    "testimony-optional": (
        ddic_ast.NormativeLayer.TESTIMONY,
        ddic_ast.FormulaPolarity.POSITIVE,
        ddic_ast.DeonticMode.OPTIONAL,
    ),
    "belief-obligatory": (
        ddic_ast.NormativeLayer.BELIEF,
        ddic_ast.FormulaPolarity.POSITIVE,
        ddic_ast.DeonticMode.OBLIGATORY,
    ),
    "belief-forbidden": (
        ddic_ast.NormativeLayer.BELIEF,
        ddic_ast.FormulaPolarity.POSITIVE,
        ddic_ast.DeonticMode.FORBIDDEN,
    ),
    "belief-optional": (
        ddic_ast.NormativeLayer.BELIEF,
        ddic_ast.FormulaPolarity.POSITIVE,
        ddic_ast.DeonticMode.OPTIONAL,
    ),
    "not-testimony-obligatory": (
        ddic_ast.NormativeLayer.TESTIMONY,
        ddic_ast.FormulaPolarity.NEGATIVE,
        ddic_ast.DeonticMode.OBLIGATORY,
    ),
    "not-testimony-forbidden": (
        ddic_ast.NormativeLayer.TESTIMONY,
        ddic_ast.FormulaPolarity.NEGATIVE,
        ddic_ast.DeonticMode.FORBIDDEN,
    ),
    "not-belief-obligatory": (
        ddic_ast.NormativeLayer.BELIEF,
        ddic_ast.FormulaPolarity.NEGATIVE,
        ddic_ast.DeonticMode.OBLIGATORY,
    ),
    "not-belief-forbidden": (
        ddic_ast.NormativeLayer.BELIEF,
        ddic_ast.FormulaPolarity.NEGATIVE,
        ddic_ast.DeonticMode.FORBIDDEN,
    ),
}

_RELATION_PREDICATES: dict[str, ddic_ast.RelationKind] = {
    "isa": ddic_ast.RelationKind.ISA,
    "before": ddic_ast.RelationKind.BEFORE,
    "before-or-equal": ddic_ast.RelationKind.BEFORE_OR_EQUAL,
    "between-inclusive": ddic_ast.RelationKind.BETWEEN_INCLUSIVE,
    "behavior-subsumes": ddic_ast.RelationKind.BEHAVIOR_SUBSUMES,
    "context-subsumes": ddic_ast.RelationKind.CONTEXT_SUBSUMES,
    "behavior-intersects": ddic_ast.RelationKind.BEHAVIOR_INTERSECTS,
    "context-intersects": ddic_ast.RelationKind.CONTEXT_INTERSECTS,
}

# AEGIS-2706 (Epic 27): v2 surface forms for plan-constraints.
# Canonical (kebab-case) names map directly to PlanConstraintKindAst;
# camelCase aliases are accepted for v1↔v2 ergonomic continuity but
# normalised to the kebab-case IR form.
_DDIC_PLAN_CONSTRAINT_PREDICATES: dict[str, ddic_ast.PlanConstraintKindAst] = {
    # Canonical kebab-case.
    "obligate-sequence": ddic_ast.PlanConstraintKindAst.OBLIGATE_SEQUENCE,
    "forbid-aggregate": ddic_ast.PlanConstraintKindAst.FORBID_AGGREGATE,
    "obligate-within": ddic_ast.PlanConstraintKindAst.OBLIGATE_WITHIN,
    "require-precondition": ddic_ast.PlanConstraintKindAst.REQUIRE_PRECONDITION,
    # camelCase aliases (parser-side normalisation only).
    "obligateSequence": ddic_ast.PlanConstraintKindAst.OBLIGATE_SEQUENCE,
    "forbidAggregate": ddic_ast.PlanConstraintKindAst.FORBID_AGGREGATE,
    "obligateWithin": ddic_ast.PlanConstraintKindAst.OBLIGATE_WITHIN,
    "requirePrecondition": ddic_ast.PlanConstraintKindAst.REQUIRE_PRECONDITION,
}

_DDIC_ONLY_PREDICATES: frozenset[str] = frozenset(
    set(_NORMATIVE_PREDICATES)
    | set(_RELATION_PREDICATES)
    | set(_DDIC_PLAN_CONSTRAINT_PREDICATES)
    | {
        "default-rule",
        "defeasible-rule",
        "priority",
        "norm-id",
        "source-id",
    }
)


def _ast_statement_from_assertion(assertion: tuple[Any, ...], span: ddic_ast.SourceSpan) -> object:
    predicate = assertion[0]
    if not isinstance(predicate, str):
        return ddic_ast.FactStatement(predicate=str(predicate), args=assertion[1:], span=span)

    if predicate in _NORMATIVE_PREDICATES:
        return _normative_ast_statement(assertion, span)
    if predicate in _RELATION_PREDICATES:
        return ddic_ast.RelationStatement(
            kind=_RELATION_PREDICATES[predicate],
            args=assertion[1:],
            span=span,
        )
    if predicate == "default-rule":
        return _default_rule_ast_statement(assertion, span)
    if predicate == "defeasible-rule":
        return _defeasible_rule_ast_statement(assertion, span)
    if predicate == "priority":
        if len(assertion) != 3:
            raise MeldSyntaxError(span.file, span.line, "priority expects exactly 2 arguments")
        return ddic_ast.PriorityStatement(
            higher=str(assertion[1]),
            lower=str(assertion[2]),
            span=span,
        )
    if predicate == "norm-id":
        if len(assertion) != 3:
            raise MeldSyntaxError(span.file, span.line, "norm-id expects exactly 2 arguments")
        return ddic_ast.NormIdStatement(norm_id=str(assertion[1]), target=assertion[2], span=span)
    if predicate == "source-id":
        if len(assertion) != 3:
            raise MeldSyntaxError(span.file, span.line, "source-id expects exactly 2 arguments")
        return ddic_ast.SourceIdStatement(
            target_id=str(assertion[1]),
            source_id=str(assertion[2]),
            span=span,
        )
    if predicate in _DDIC_PLAN_CONSTRAINT_PREDICATES:
        return _plan_constraint_ast_statement(assertion, span)
    return ddic_ast.FactStatement(predicate=predicate, args=assertion[1:], span=span)


def _plan_constraint_ast_statement(
    assertion: tuple[Any, ...],
    span: ddic_ast.SourceSpan,
) -> ddic_ast.PlanConstraintStatement:
    """Build a PlanConstraintStatement from a v2 assertion (AEGIS-2706).

    The parser keeps things permissive: it normalises camelCase to
    kebab-case via ``_DDIC_PLAN_CONSTRAINT_PREDICATES`` and validates
    only the arity. Per-kind semantic checks (integer thresholds,
    timeframe symbols, precondition shape) live in the IR-compile
    step so the verification pipeline can emit several diagnostics
    per file in one pass (AEGIS-2707).
    """
    predicate = str(assertion[0])
    kind = _DDIC_PLAN_CONSTRAINT_PREDICATES[predicate]
    if len(assertion) != 3:
        raise MeldSyntaxError(
            span.file,
            span.line,
            f"{predicate} expects exactly 2 arguments, got {len(assertion) - 1}",
        )
    return ddic_ast.PlanConstraintStatement(
        kind=kind,
        args=assertion[1:],
        span=span,
    )


def _normative_ast_statement(
    assertion: tuple[Any, ...],
    span: ddic_ast.SourceSpan,
) -> ddic_ast.NormativeFormulaStatement:
    predicate = str(assertion[0])
    if len(assertion) != 5:
        raise MeldSyntaxError(span.file, span.line, f"{predicate} expects exactly 4 arguments")
    layer, polarity, mode = _NORMATIVE_PREDICATES[predicate]
    formula = ddic_ast.NormativeFormula(
        layer=layer,
        polarity=polarity,
        mode=mode,
        agent=assertion[1],
        behavior=assertion[2],
        context=assertion[3],
        time=assertion[4],
        span=span,
    )
    return ddic_ast.NormativeFormulaStatement(formula=formula, span=span)


def _default_rule_ast_statement(
    assertion: tuple[Any, ...],
    span: ddic_ast.SourceSpan,
) -> ddic_ast.DefaultRuleStatement:
    if len(assertion) != 3:
        raise MeldSyntaxError(span.file, span.line, "default-rule expects rule id and rule form")
    rule_id = str(assertion[1])
    raw = _compound_from_value(assertion[2], span)
    head: Any = raw
    body: tuple[Any, ...] = ()
    if raw.head in {"implies", "iff"} and len(raw.args) >= 2:
        body = (raw.args[0],)
        head = raw.args[1]
    return ddic_ast.DefaultRuleStatement(
        rule_id=rule_id,
        head=head,
        body=body,
        raw_form=raw,
        span=span,
    )


def _defeasible_rule_ast_statement(
    assertion: tuple[Any, ...],
    span: ddic_ast.SourceSpan,
) -> ddic_ast.DefeasibleRuleStatement:
    if len(assertion) < 2:
        raise MeldSyntaxError(span.file, span.line, "defeasible-rule expects at least a rule id")
    rule_id = str(assertion[1])
    fields = _keyword_fields(assertion[2:], span)
    from_formula = fields.get(":from")
    to_formula = fields.get(":to")
    when_value = fields.get(":when", ())
    justification_value = fields.get(":justification", ())
    defeat_mode_value = fields.get(":defeat-mode")
    if from_formula is None or to_formula is None:
        raise MeldSyntaxError(span.file, span.line, "defeasible-rule requires :from and :to")

    when_conditions = _tuple_items(when_value)
    justification_conditions = _tuple_items(justification_value)
    defeat_mode: ddic_ast.DefeatMode | None = None
    if defeat_mode_value is not None:
        mode_name = str(defeat_mode_value)
        try:
            defeat_mode = ddic_ast.DefeatMode(mode_name)
        except ValueError:
            raise MeldSyntaxError(
                span.file, span.line, f"Unknown defeat mode: {mode_name}"
            ) from None

    return ddic_ast.DefeasibleRuleStatement(
        rule_id=rule_id,
        from_formula=from_formula,
        to_formula=to_formula,
        when_conditions=when_conditions,
        justification_conditions=justification_conditions,
        defeat_mode=defeat_mode,
        span=span,
    )


def _keyword_fields(items: tuple[Any, ...], span: ddic_ast.SourceSpan) -> dict[str, Any]:
    if len(items) % 2 != 0:
        raise MeldSyntaxError(span.file, span.line, "Expected keyword/value pairs")
    fields: dict[str, Any] = {}
    for i in range(0, len(items), 2):
        key = items[i]
        if not isinstance(key, str) or not key.startswith(":"):
            raise MeldSyntaxError(span.file, span.line, f"Expected keyword field, got {key!r}")
        fields[key] = items[i + 1]
    return fields


def _tuple_items(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    return ()


def _compound_from_value(value: Any, span: ddic_ast.SourceSpan) -> ddic_ast.CompoundTerm:
    if not isinstance(value, tuple) or not value:
        raise MeldSyntaxError(span.file, span.line, "Expected compound expression")
    head = value[0]
    if not isinstance(head, str):
        raise MeldSyntaxError(span.file, span.line, "Compound head must be a symbol")
    return ddic_ast.CompoundTerm(head=head, args=value[1:], span=span)


# ── Norm Extraction ──────────────────────────────────────────────────


def extract_norm(
    assertion: tuple[Any, ...],
    current_mt: str,
    source: str,
) -> NormFrame | None:
    """Extract a NormFrame from a deontic assertion, or return None.

    Validates arity per _DEONTIC_ARITY.  Returns None for non-deontic assertions.

    Raises:
        MeldSyntaxError: If a deontic predicate has wrong arity.
    """
    if not assertion or not isinstance(assertion[0], str):
        return None

    predicate = assertion[0]
    if predicate not in DEONTIC_PREDICATES:
        return None

    expected_arity = _DEONTIC_ARITY[predicate]
    actual_arity = len(assertion) - 1
    if actual_arity != expected_arity:
        raise MeldSyntaxError(
            source,
            0,
            f"{predicate} expects {expected_arity} arguments, got {actual_arity}",
        )

    modality = DeonticModality.from_meld_predicate(predicate)

    # Route by family:
    # ToBe (arity 1): no agent, no code
    if predicate in ("oughtToBe", "forbiddenToBe", "permittedToBe"):
        prop = assertion[1]
        return NormFrame(
            code="",
            agent_pattern="*",
            modality=modality,
            proposition=_to_prop(prop),
            source=source,
        )

    # ToDo (arity 2): agent, no code
    if predicate in ("oughtToDo", "forbiddenToDo", "permittedToDo"):
        agent = str(assertion[1])
        prop = assertion[2]
        return NormFrame(
            code="",
            agent_pattern=agent,
            modality=modality,
            proposition=_to_prop(prop),
            source=source,
        )

    # ToDo-WRT (arity 3): code, agent, proposition
    code = str(assertion[1])
    agent = str(assertion[2])
    prop = assertion[3]
    return NormFrame(
        code=code,
        agent_pattern=agent,
        modality=modality,
        proposition=_to_prop(prop),
        source=source,
    )


def _to_prop(value: Any) -> tuple[Any, ...]:
    """Ensure a proposition is a tuple."""
    if isinstance(value, tuple):
        return value
    return (value,)


def extract_plan_constraint(
    assertion: tuple[Any, ...],
    current_mt: str,  # noqa: ARG001 — reserved for AEGIS-2706 v2 extension
    source: str,
) -> PlanNormFrame | None:
    """Extract a PlanNormFrame from a plan-constraint assertion.

    AEGIS-2704: Validates arity and per-kind argument types. Returns
    None for non-plan-constraint assertions so the caller can chain.

    Per-kind validation:

    - ``forbidAggregate``: ``?max-count`` must be an integer ≥ 0.
    - ``obligateWithin``: ``?timeframe`` must be either a non-negative
      integer (seconds) or one of the symbolic timeframes
      ``immediate``, ``same-session``, ``end-of-plan``.
    - ``obligateSequence`` and ``requirePrecondition`` accept any
      shape at this stage; symbol-resolution happens in the
      VerificationPipeline (AEGIS-2707).

    The unknown-action-type warning is intentionally NOT emitted here
    — it is the verification pipeline's job. v1 stays consistent with
    the existing practice of soft-warning rather than hard-erroring on
    unresolved symbols.

    Raises:
        MeldSyntaxError: with ``source`` as file context if a
            plan-constraint predicate has wrong arity or invalid
            argument shape.
    """
    if not assertion or not isinstance(assertion[0], str):
        return None

    predicate = assertion[0]
    if predicate not in PLAN_CONSTRAINT_PREDICATES:
        return None

    expected_arity = _PLAN_CONSTRAINT_ARITY[predicate]
    actual_arity = len(assertion) - 1
    if actual_arity != expected_arity:
        raise MeldSyntaxError(
            source,
            0,
            f"{predicate} expects {expected_arity} arguments, "
            f"got {actual_arity}",
        )

    args = tuple(assertion[1:])

    if predicate == "forbidAggregate":
        max_count = args[1]
        # bool is an int subclass — explicitly reject to avoid surprise.
        if isinstance(max_count, bool) or not isinstance(max_count, int):
            raise MeldSyntaxError(
                source,
                0,
                f"forbidAggregate ?max-count must be an integer, "
                f"got {type(max_count).__name__}: {max_count!r}",
            )
        if max_count < 0:
            raise MeldSyntaxError(
                source,
                0,
                f"forbidAggregate ?max-count must be >= 0, got {max_count}",
            )
    elif predicate == "obligateWithin":
        timeframe = args[1]
        if isinstance(timeframe, bool):
            raise MeldSyntaxError(
                source,
                0,
                f"obligateWithin ?timeframe must be a string symbol or "
                f"a non-negative integer, got bool: {timeframe!r}",
            )
        if isinstance(timeframe, int):
            if timeframe < 0:
                raise MeldSyntaxError(
                    source,
                    0,
                    f"obligateWithin numeric ?timeframe must be >= 0, "
                    f"got {timeframe}",
                )
        elif isinstance(timeframe, str):
            if timeframe not in _VALID_TIMEFRAME_SYMBOLS:
                allowed = ", ".join(sorted(_VALID_TIMEFRAME_SYMBOLS))
                raise MeldSyntaxError(
                    source,
                    0,
                    f"obligateWithin ?timeframe must be one of "
                    f"[{allowed}] or a non-negative integer, "
                    f"got {timeframe!r}",
                )
        else:
            raise MeldSyntaxError(
                source,
                0,
                f"obligateWithin ?timeframe must be a string symbol or "
                f"a non-negative integer, got "
                f"{type(timeframe).__name__}",
            )

    return PlanNormFrame(predicate=predicate, args=args, source=source)


# ── Full Loader ──────────────────────────────────────────────────────


class MeldLoader:
    """Load .meld files (Modal Ethics Logic Definitions) into a KnowledgeBase.

    Usage::

        from aegis.kb.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        loader = MeldLoader(kb)
        loader.load_file(Path("domain/ontology.meld"))
        loader.load_file(Path("domain/rules.meld"))
        kb.freeze()
    """

    def __init__(self, kb: KnowledgeBase) -> None:
        self._kb = kb
        self._norms: list[NormFrame] = []
        self._code_prevalence: list[str] | None = None
        # AEGIS-2704: plan-level constraints, kept in load order.
        self._plan_constraints: list[PlanNormFrame] = []
        self._schema_version: int | None = None
        # AEGIS-2901: track disambiguation edges across all files for
        # post-load consistency checks. Each entry is (file, line).
        self._narrower_edges: list[tuple[str, str, str]] = []
        self._broader_edges: list[tuple[str, str, str]] = []

    @property
    def norms(self) -> list[NormFrame]:
        """All NormFrames extracted during loading."""
        return list(self._norms)

    @property
    def code_prevalence(self) -> list[str] | None:
        """Explicit v1 code order from MELD, highest first; absent preserves defaults."""
        if self._code_prevalence is None:
            return None
        known = {n.code for n in self._norms if n.code}
        known.update(str(f[1]) for f in self._kb.query(("isa", "?code", "CodeOfConduct")))
        if any(code not in known for code in self._code_prevalence):
            raise ValueError("codePrevalence references an undeclared code of conduct")
        return list(self._code_prevalence)

    @property
    def plan_constraints(self) -> list[PlanNormFrame]:
        """All PlanNormFrames extracted during loading (AEGIS-2704)."""
        return list(self._plan_constraints)

    @property
    def schema_version(self) -> int | None:
        return self._schema_version

    def load_file(self, path: Path) -> None:
        """Load a single .meld file into the KB."""
        text = path.read_text(encoding="utf-8")
        self.load_string(text, file=str(path))

    def load_string(self, text: str, file: str = "<string>") -> None:
        """Load .meld content from a string."""
        assertions = parse_meld(text, file)
        current_mt: str | None = None
        line_counter = 0

        for assertion in assertions:
            line_counter += 1
            predicate = assertion[0] if assertion else None

            # (case MtName) — context switch
            if predicate == "case":
                if len(assertion) != 2:
                    raise MeldSyntaxError(file, 0, "case expects exactly 1 argument")
                mt_name = str(assertion[1])
                current_mt = mt_name
                if self._kb.get_mt(mt_name) is None:
                    self._kb.create_mt(mt_name)
                continue

            # (aegis-schema-version N)
            if predicate == "aegis-schema-version":
                if len(assertion) != 2:
                    raise MeldSyntaxError(
                        file, 0, "aegis-schema-version expects exactly 1 argument"
                    )
                version = assertion[1]
                if not isinstance(version, int) or version < 1:
                    raise MeldSyntaxError(file, 0, f"Unknown schema version: {version}")
                if version > 1:
                    raise MeldSyntaxError(
                        file, 0, f"Unknown schema version: {version} (supported: 1)"
                    )
                self._schema_version = version
                continue

            # All other assertions require an active Mt
            if current_mt is None:
                raise MeldSyntaxError(file, 0, "No microtheory declared (missing 'case')")

            if predicate == "codePrevalence":
                codes = assertion[1:]
                if (self._code_prevalence is not None or not codes
                    or any(not isinstance(code, str) for code in codes)
                    or len(set(codes)) != len(codes)):
                    raise MeldSyntaxError(file, line_counter,
                                          "Declare one unique, nonempty codePrevalence order")
                self._code_prevalence = [str(code) for code in codes]
                self._kb.assert_fact(assertion, current_mt)
                continue

            # Assert into KB
            source = f"{file}:{line_counter}"
            self._kb.assert_fact(assertion, current_mt)

            # AEGIS-2901: collect Subsumption edges for post-load
            # consistency check (bidirectional + acyclic).
            if isinstance(predicate, str) and predicate in {"narrowerThan", "broaderThan"}:
                if len(assertion) != 3:
                    raise MeldSyntaxError(
                        file, 0,
                        f"{predicate} expects exactly 2 arguments",
                    )
                left = str(assertion[1])
                right = str(assertion[2])
                if predicate == "narrowerThan":
                    self._narrower_edges.append((left, right, source))
                else:
                    self._broader_edges.append((left, right, source))

            # Extract NormFrame if deontic
            if isinstance(predicate, str) and predicate in DEONTIC_PREDICATES:
                norm = extract_norm(assertion, current_mt, source)
                if norm is not None:
                    self._norms.append(norm)
            elif (
                isinstance(predicate, str)
                and predicate in PLAN_CONSTRAINT_PREDICATES
            ):
                # AEGIS-2704: plan-constraint predicates have their own
                # arity + per-kind validation. The assertion has already
                # been stored as a generic fact above; here we only
                # extract the typed frame for downstream compilation.
                frame = extract_plan_constraint(assertion, current_mt, source)
                if frame is not None:
                    self._plan_constraints.append(frame)
            elif isinstance(predicate, str) and predicate not in _KNOWN_PREDICATES:
                logger.warning(
                    "Unknown predicate %r in %s. Stored as generic fact, "
                    "not interpreted as deontic assertion.",
                    predicate,
                    source,
                )

    def validate_disambiguation_graph(self) -> None:
        """Validate Subsumption-Konsistenz nach AEGIS-2901, MELD-Spec § 3.4.1.

        Thin wrapper around the free ``check_disambiguation_graph`` so
        v1 callers (MeldLoader) and v2 callers (Guard.from_meld_ddic_files)
        share the same validator. See AEGIS-2902.
        """
        check_disambiguation_graph(self._narrower_edges, self._broader_edges)


# All predicates from CYCL_PARSER_GRAMMAR.md §7.
_KNOWN_PREDICATES: frozenset[str] = frozenset(
    {
        # Special
        "case",
        "aegis-schema-version",
        # Core ontology
        "isa",
        "genls",
        "genlPreds",
        "negationPreds",
        "typeGenls",
        "comment",
        # Arg constraints
        "argIsa",
        "arg1Isa",
        "arg2Isa",
        "arg2QuotedIsa",
        "arg3QuotedIsa",
        "argQuotedIsa",
        "arg1Genl",
        "arg2Genl",
        "argGenl",
        "resultGenl",
        "quotedIsa",
        # Deontic ToDo
        "oughtToDo",
        "forbiddenToDo",
        "permittedToDo",
        "oughtToDo-WRT",
        "forbiddenToDo-WRT",
        "permittedToDo-WRT",
        # Deontic ToBe
        "oughtToBe",
        "forbiddenToBe",
        "permittedToBe",
        # Metadata
        "sharedNotes",
        "singleEntryFormatInArgs",
        "functionCorrespondingPredicate-Canonical",
        "argFormat",
        "arg2Format",
        # AEGIS extensions
        "actionParameter",
        "requiredContext",
        # Action-Substitution disambiguation (AEGIS-2901, Epic 29).
        # Loader-side consistency + acyclicity is validated by
        # ``MeldLoader.validate_disambiguation_graph`` after freeze.
        "actionDescription",
        "actionSynonym",
        "notToBeConfusedWith",
        "narrowerThan",
        "broaderThan",
        # Plan-Level Governance plan-constraints (AEGIS-2704, Epic 27).
        # Listed here so the unknown-predicate warning does not fire;
        # extraction into PlanNormFrame happens in load_string.
        "obligateSequence",
        "forbidAggregate",
        "obligateWithin",
        "requirePrecondition",
    }
)


# ── Action-Substitution disambiguation predicates (AEGIS-2901) ──

DISAMBIGUATION_PREDICATES: frozenset[str] = frozenset(
    {
        "actionDescription",
        "actionSynonym",
        "notToBeConfusedWith",
        "narrowerThan",
        "broaderThan",
    }
)


def check_disambiguation_graph(
    narrower_edges: list[tuple[str, str, str]],
    broader_edges: list[tuple[str, str, str]],
) -> None:
    """Validate Subsumption invariants for AEGIS-2901 / Epic 29.

    Each edge tuple is ``(left, right, source)`` where ``source`` is a
    ``"file:line"`` string used in error messages.

    Two invariants enforced:

    1. **Bidirektional**: every ``(narrowerThan A B)`` must be mirrored
       by ``(broaderThan B A)``, and vice versa.
    2. **Azyklisch**: the directed graph induced by ``narrowerThan``
       must be a DAG.

    Raises:
        MeldSyntaxError: with the offending file and a clear diagnostic
            on the first violation found. AEGIS-2902 makes this the
            single shared validator across v1 and v2 load paths.
    """
    narrower_set = {(a, b) for a, b, _ in narrower_edges}
    broader_inverse = {(b, a) for a, b, _ in broader_edges}

    for left, right, source in narrower_edges:
        if (left, right) not in broader_inverse:
            raise MeldSyntaxError(
                source.split(":")[0], 0,
                f"narrowerThan {left} {right} has no matching "
                f"(broaderThan {right} {left}) — see docs/_archive/MELD_SPEC.md § 3.4.1.",
            )

    for left, right, source in broader_edges:
        if (right, left) not in narrower_set:
            raise MeldSyntaxError(
                source.split(":")[0], 0,
                f"broaderThan {left} {right} has no matching "
                f"(narrowerThan {right} {left}) — see docs/_archive/MELD_SPEC.md § 3.4.1.",
            )

    graph: dict[str, list[str]] = {}
    for a, b, _ in narrower_edges:
        graph.setdefault(a, []).append(b)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in graph}
    for node in list(graph.keys()):
        if color.get(node, WHITE) != WHITE:
            continue
        stack: list[tuple[str, int]] = [(node, 0)]
        while stack:
            current, idx = stack[-1]
            if idx == 0:
                color[current] = GRAY
            neighbours = graph.get(current, [])
            if idx >= len(neighbours):
                color[current] = BLACK
                stack.pop()
                continue
            stack[-1] = (current, idx + 1)
            child = neighbours[idx]
            if color.get(child, WHITE) == GRAY:
                raise MeldSyntaxError(
                    "<disambiguation-graph>", 0,
                    f"Cycle in narrowerThan graph at edge "
                    f"{current} → {child} — see docs/_archive/MELD_SPEC.md § 3.4.1.",
                )
            if color.get(child, WHITE) == WHITE:
                stack.append((child, 0))
                color.setdefault(child, WHITE)


def collect_disambiguation_edges(
    assertions: list[tuple[object, ...]],
    file: str,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Extract narrower/broader edges from a parsed assertion list.

    Used by the v2 load path (which does not go through MeldLoader) to
    feed ``check_disambiguation_graph``. Lines are not tracked here —
    the parser does not preserve them in this projection — so all
    edges share ``file:0`` as their source.
    """
    narrower: list[tuple[str, str, str]] = []
    broader: list[tuple[str, str, str]] = []
    for assertion in assertions:
        if not assertion or not isinstance(assertion[0], str):
            continue
        head = assertion[0]
        if head not in {"narrowerThan", "broaderThan"}:
            continue
        if len(assertion) != 3:
            raise MeldSyntaxError(
                file, 0, f"{head} expects exactly 2 arguments",
            )
        left = str(assertion[1])
        right = str(assertion[2])
        if head == "narrowerThan":
            narrower.append((left, right, f"{file}:0"))
        else:
            broader.append((left, right, f"{file}:0"))
    return narrower, broader
