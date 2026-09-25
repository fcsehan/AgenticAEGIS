"""PlanNormFrame — v1 intermediate representation of a plan-level
constraint (AEGIS-2704, Epic 27).

Sits between MELD parsing (`aegis.kb.meld_loader.extract_plan_constraint`)
and DDIC compilation (`aegis.engine.normframe_compile`). One PlanNormFrame
per recognised plan-constraint predicate; downstream compilation produces
exactly one DDICPlanConstraint per frame.

Despite the DDIC-prefixed target type, plan constraints are evaluated by
AEGIS' plan layer. Olson's DDIC conflict calculus remains the action-norm
reasoner; the plan layer composes those action verdicts with sequence,
aggregate, timing, and precondition constraints.

The four canonical v1 predicates (all arity 2):

- ``(obligateSequence ?predecessor ?successor)``
- ``(forbidAggregate ?action-type ?max-count)`` — int max-count ≥ 0
- ``(obligateWithin ?action-type ?timeframe)`` — symbol or int
- ``(requirePrecondition ?action-type ?precondition)`` — state predicate

PlanNormFrame is frozen + slotted for the same hashability guarantees as
NormFrame (D-005). The compilation step is lossless: the source-ref is
preserved end-to-end so verifier diagnostics can point back to the .meld
line that introduced the constraint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PlanNormFrame:
    """A single plan-constraint extracted from a v1 .meld file.

    Attributes:
        predicate: The plan-constraint predicate name. One of:
            ``"obligateSequence"``, ``"forbidAggregate"``,
            ``"obligateWithin"``, ``"requirePrecondition"``.
        args: The raw arguments tuple as parsed from the .meld
            S-expression (e.g. ``("deploy", 3)`` for a
            ``forbidAggregate``). Compilation in AEGIS-2705 maps this
            into the typed ``DDICPlanConstraint.args`` (DDICTerm tuple).
        agent_pattern: Pattern describing which agents this constraint
            scopes to. v1 surface form has no agent slot, so the default
            ``"*"`` (any agent) applies; v2 will permit explicit scoping
            via the AST.
        code: CodeOfConduct identifier (analogous to NormFrame.code).
            Empty for code-independent plan-constraints.
        specificity: Inheritance depth, reserved for downstream
            conflict-resolution (parallel to NormFrame.specificity).
        defeasible: Whether this constraint can be overridden by a more
            specific constraint. Default True; non-defeasible
            plan-constraints would correspond to plan-level moral
            axioms (I4) — left as Phase 4 future work in Epic 27.
        source: Provenance string ``"file:line"`` carried verbatim
            into ``DDICPlanConstraint.source_ref`` so verifier and
            audit tooling can resolve diagnostics back to the .meld
            line.
    """

    predicate: str
    args: tuple[Any, ...]
    agent_pattern: str = "*"
    code: str = ""
    specificity: int = 0
    defeasible: bool = True
    source: str = ""
