"""Compile v1 NormFrames into the unified DDICModule IR.

This module bridges the legacy v1 MELD pipeline (NormFrame-based) into the
unified DDICModule representation.  Every v1 NormFrame maps losslessly to a
DDICFormula.  The resulting DDICModule carries ``resolution_strategy="legacy"``
so the evaluator knows to apply the v1 6-step algorithm.

Mapping rules:
    - layer   → always TESTIMONY (v1 has no testimony/belief distinction)
    - polarity → always POSITIVE (v1 has no negation predicates)
    - mode    → OBLIGATORY / FORBIDDEN / OPTIONAL (PERMITTED maps to OPTIONAL)
    - agent   → DDICSymbol(agent_pattern)
    - behavior → proposition tuple → DDICCompound or DDICSymbol
    - context → DDICSymbol("Top")  (v1 has no context dimension)
    - time    → DDICSymbol("t0")   (v1 has no temporal ordering)
    - code    → DDICMetadata(key="code", formula_id, value)
    - defeasible=False → DDICMetadata(key="is_axiom", formula_id, "true")
"""

from __future__ import annotations

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.deontic.plan_norm_frame import PlanNormFrame
from aegis.engine.ddic_ir import (
    DDICCompound,
    DDICFormula,
    DDICInteger,
    DDICLayer,
    DDICMetadata,
    DDICMode,
    DDICModule,
    DDICPlanConstraint,
    DDICPolarity,
    DDICRelation,
    DDICRelationKind,
    DDICSymbol,
    DDICTerm,
    PlanConstraintKind,
)
from aegis.kb.knowledge_base import KnowledgeBase

# Sentinel symbols for v1 defaults.
_TOP = DDICSymbol("Top")
_T0 = DDICSymbol("t0")

# v1 DeonticModality → v2 DDICMode.
_MODALITY_TO_MODE: dict[DeonticModality, DDICMode] = {
    DeonticModality.OBLIGATORY: DDICMode.OBLIGATORY,
    DeonticModality.FORBIDDEN: DDICMode.FORBIDDEN,
    DeonticModality.PERMITTED: DDICMode.OPTIONAL,
}


def compile_norms_to_module(
    norms: list[NormFrame],
    kb: KnowledgeBase | None = None,
    code_prevalence: list[str] | None = None,
    plan_constraints: list[PlanNormFrame] | None = None,
) -> DDICModule:
    """Compile a list of v1 NormFrames into a unified DDICModule.

    The module carries ``resolution_strategy="legacy"`` so that the unified
    evaluator applies the v1 6-step conflict resolution algorithm.

    Args:
        norms: Extracted NormFrames (may already have specificity assigned).
        kb: Optional KnowledgeBase for extracting genls/isa relations.
        code_prevalence: Optional code ordering for cross-code tie-breaking.
        plan_constraints: AEGIS-2705 (Epic 27). Optional list of v1
            PlanNormFrames (extracted by ``MeldLoader``); each frame is
            compiled losslessly into a ``DDICPlanConstraint`` and
            attached to the resulting module's ``plan_constraints``.
            ``None`` (the default) is identical to an empty list — the
            existing 6 v1 domains and the 1300+ regression tests are
            byte-identical to the pre-2705 output for plan-constraint-
            free input.

    Returns:
        A DDICModule with formulas, relations, metadata, and (optionally)
        plan_constraints.
    """
    formulas: list[DDICFormula] = []
    metadata: list[DDICMetadata] = []
    relations: list[DDICRelation] = []

    for norm in norms:
        formula = _norm_to_formula(norm)
        formulas.append(formula)

        # Track code association as metadata.
        if norm.code:
            metadata.append(
                DDICMetadata(
                    key="code",
                    value=DDICSymbol(norm.code),
                    source_ref=formula.formula_id,
                )
            )

        # Track moral axiom status as metadata.
        if not norm.defeasible:
            metadata.append(
                DDICMetadata(
                    key="is_axiom",
                    value=DDICSymbol("true"),
                    source_ref=formula.formula_id,
                )
            )

        # Store specificity from InheritanceGraph assignment.
        if norm.specificity != 0:
            metadata.append(
                DDICMetadata(
                    key="specificity",
                    value=DDICSymbol(str(norm.specificity)),
                    source_ref=formula.formula_id,
                )
            )

    # Extract genls/isa relations from KB for subsumption.
    if kb is not None:
        relations = _extract_relations_from_kb(kb)

    compiled_plan_constraints = compile_plan_constraints_to_module(
        plan_constraints or []
    )

    return DDICModule(
        formulas=tuple(formulas),
        relations=tuple(relations),
        defaults=(),
        defeasible_rules=(),
        priorities=(),
        metadata=tuple(metadata),
        resolution_strategy="legacy",
        code_prevalence=tuple(code_prevalence) if code_prevalence else (),
        plan_constraints=compiled_plan_constraints,
    )


# ── Plan-Constraint Compilation (AEGIS-2705, Epic 27) ───────────────


# Mapping per AEGIS-2705 acceptance: each predicate fixes (kind,
# layer, mode, polarity). The choices follow Olson's reading: a
# sequence/within/precondition is an obligation; an aggregate cap is
# a forbid; preconditions live on the BELIEF layer because they
# query state, not testimony.
_PLAN_CONSTRAINT_MAPPING: dict[
    str, tuple[PlanConstraintKind, DDICLayer, DDICMode, DDICPolarity]
] = {
    "obligateSequence": (
        PlanConstraintKind.OBLIGATE_SEQUENCE,
        DDICLayer.TESTIMONY,
        DDICMode.OBLIGATORY,
        DDICPolarity.POSITIVE,
    ),
    "forbidAggregate": (
        PlanConstraintKind.FORBID_AGGREGATE,
        DDICLayer.TESTIMONY,
        DDICMode.FORBIDDEN,
        DDICPolarity.POSITIVE,
    ),
    "obligateWithin": (
        PlanConstraintKind.OBLIGATE_WITHIN,
        DDICLayer.TESTIMONY,
        DDICMode.OBLIGATORY,
        DDICPolarity.POSITIVE,
    ),
    "requirePrecondition": (
        PlanConstraintKind.REQUIRE_PRECONDITION,
        DDICLayer.BELIEF,
        DDICMode.OBLIGATORY,
        DDICPolarity.POSITIVE,
    ),
}


def compile_plan_constraints_to_module(
    frames: list[PlanNormFrame],
) -> tuple[DDICPlanConstraint, ...]:
    """Compile a list of v1 PlanNormFrames into typed DDICPlanConstraints.

    These constraints share the ``DDICModule`` container with action
    formulas, but are consumed by the plan evaluator rather than by the
    DDIC conflict-resolution rules themselves.

    Lossless: ``frame.predicate`` selects the IR ``kind``; ``frame.args``
    is term-compiled element-wise; ``frame.agent_pattern`` becomes
    ``agent_pattern`` (default ``DDICSymbol("*")``); ``frame.source``
    becomes ``source_ref``. ``frame.specificity`` and ``frame.defeasible``
    pass through unchanged.

    The returned tuple is in input order so verifier diagnostics keep
    referring to the .meld lines in declaration order.
    """
    constraints: list[DDICPlanConstraint] = []
    for index, frame in enumerate(frames):
        if frame.predicate not in _PLAN_CONSTRAINT_MAPPING:
            # Defensive — the loader should never emit an unrecognised
            # predicate, but if a future MELD extension adds one we
            # surface it loudly rather than dropping the constraint.
            raise ValueError(
                f"Unrecognised plan-constraint predicate {frame.predicate!r} "
                f"at {frame.source} — _PLAN_CONSTRAINT_MAPPING is out of sync.",
            )
        kind, layer, mode, polarity = _PLAN_CONSTRAINT_MAPPING[frame.predicate]
        constraint_id = f"plan-{frame.predicate}:{index}"
        agent_pattern = DDICSymbol(frame.agent_pattern or "*")
        compiled_args = tuple(_plan_arg_to_term(a) for a in frame.args)
        constraints.append(
            DDICPlanConstraint(
                constraint_id=constraint_id,
                kind=kind,
                args=compiled_args,
                layer=layer,
                mode=mode,
                polarity=polarity,
                source_ref=frame.source,
                agent_pattern=agent_pattern,
                specificity=frame.specificity,
                defeasible=frame.defeasible,
            )
        )
    return tuple(constraints)


def _plan_arg_to_term(value: object) -> DDICTerm:
    """Convert a plan-constraint argument to a DDIC term.

    Mirrors ``aegis.engine.ddic_ir._compile_term`` but is local so the
    v1 compat path stays free of v2-AST imports. Strings → DDICSymbol,
    ints → DDICInteger, tuples → DDICCompound (recursive). bool is
    rejected (it's an int subclass; the loader already filters this
    out for forbidAggregate but a defensive check here keeps the
    invariant local).
    """
    if isinstance(value, bool):
        raise ValueError(f"bool is not a valid DDIC term: {value!r}")
    if isinstance(value, int):
        return DDICInteger(value)
    if isinstance(value, str):
        return DDICSymbol(value)
    if isinstance(value, tuple) and value:
        head = value[0]
        if not isinstance(head, str):
            raise ValueError(f"Compound head must be a string: {value!r}")
        return DDICCompound(
            head=head,
            args=tuple(_plan_arg_to_term(a) for a in value[1:]),
        )
    raise ValueError(f"Unsupported plan-constraint argument: {value!r}")


def _norm_to_formula(norm: NormFrame) -> DDICFormula:
    """Convert a single NormFrame to a DDICFormula."""
    return DDICFormula(
        formula_id=norm.source or f"norm:{id(norm)}",
        layer=DDICLayer.TESTIMONY,
        mode=_MODALITY_TO_MODE[norm.modality],
        polarity=DDICPolarity.POSITIVE,
        agent=DDICSymbol(norm.agent_pattern),
        behavior=_proposition_to_behavior(norm.proposition),
        context=_TOP,
        time=_T0,
        source_ref=norm.source,
    )


def _proposition_to_behavior(prop: tuple[object, ...]) -> DDICTerm:
    """Convert a v1 proposition tuple to a DDICTerm.

    Single-element propositions become DDICSymbol.
    Multi-element propositions become DDICCompound(head, args).
    """
    if len(prop) == 1:
        return DDICSymbol(str(prop[0]))
    head = str(prop[0])
    args = tuple(DDICSymbol(str(arg)) for arg in prop[1:])
    return DDICCompound(head=head, args=args)


def _extract_relations_from_kb(kb: KnowledgeBase) -> list[DDICRelation]:
    """Extract genls and isa facts from the KB as DDICRelations."""
    relations: list[DDICRelation] = []
    counter = 0

    for mt_name in kb.microtheories:
        for fact in kb.facts_in_mt(mt_name):
            if not fact or not isinstance(fact[0], str):
                continue
            pred = fact[0]
            if pred == "genls" and len(fact) == 3:
                counter += 1
                relations.append(
                    DDICRelation(
                        relation_id=f"kb:genls:{counter}",
                        kind=DDICRelationKind.ISA,
                        args=(DDICSymbol(str(fact[1])), DDICSymbol(str(fact[2]))),
                        source_ref=f"kb:{mt_name}",
                    )
                )
            elif pred == "isa" and len(fact) == 3:
                counter += 1
                relations.append(
                    DDICRelation(
                        relation_id=f"kb:isa:{counter}",
                        kind=DDICRelationKind.ISA,
                        args=(DDICSymbol(str(fact[1])), DDICSymbol(str(fact[2]))),
                        source_ref=f"kb:{mt_name}",
                    )
                )

    return relations


def formula_code(formula: DDICFormula, module: DDICModule) -> str:
    """Look up the CodeOfConduct for a formula from module metadata."""
    for m in module.metadata:
        if m.key == "code" and m.source_ref == formula.formula_id:
            if isinstance(m.value, DDICSymbol):
                return m.value.value
    return ""


def formula_is_axiom(formula: DDICFormula, module: DDICModule) -> bool:
    """Check if a formula is a non-defeasible moral axiom."""
    for m in module.metadata:
        if m.key == "is_axiom" and m.source_ref == formula.formula_id:
            return True
    return False
