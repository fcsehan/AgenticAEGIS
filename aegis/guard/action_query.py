"""Action → DDIC query-term mapping (AEGIS-2313).

Defines the **explicit, declared** mapping strategy from a guard-level
``Action`` to the three DDIC query coordinates that the evaluator needs:

- ``behavior`` term  — what the agent intends to do
- ``context`` term   — under which application context
- ``time`` term      — at which point in the time relation

The previous implementation used an ad-hoc ``action.context["ddic_context"]``
string lookup with a ``"Top"`` default and no time support. That worked for
the IAMission demo but did not scale — the Plan-Evaluator (Epic 27) and
domain-specific norms need a documented contract for how an Action's payload
is converted into DDIC query terms.

## Mapping rules

Behavior
    If the action's ``ActionType`` schema declares parameters, the behavior
    is a ``DDICCompound`` whose head is the action type and whose args are
    the schema-ordered proposition values. Without parameters, the behavior
    is a bare ``DDICSymbol(action.action_type)``. This logic lives in
    ``action_behavior``.

Context
    Read from ``action.context[CONTEXT_KEY]`` with default ``"Top"`` (the
    universal application context — every belief subsumes Top). The key
    name is the module-level constant ``CONTEXT_KEY``; setting it via the
    domain's action vocabulary (rather than free-text in the proposition)
    keeps the contract explicit. Defined by ``action_context``.

Time
    Read from ``action.context[TIME_KEY]`` with default ``"tn"`` (the
    canonical "now" symbol used in MELD belief assertions). The default
    matches the convention used in the bundled domain rule sets. Defined
    by ``action_time``.

Both context and time are surfaced as opaque ``DDICTerm`` instances
(``DDICSymbol`` / ``DDICInteger`` / ``DDICCompound``) — the evaluator does
not require strings.

## Why this lives in its own module

The mapping is shared by ``aegis/guard/pipeline.py`` (unified path) and
``aegis/guard/ddic_pipeline.py`` (legacy v2 entry). Centralising avoids
silent drift between the two paths and gives Epic 27's plan-evaluator a
single import target when it needs to map plan-step actions to DDIC
queries.
"""

from __future__ import annotations

from aegis.engine.ddic_ir import DDICCompound, DDICInteger, DDICSymbol, DDICTerm
from aegis.guard.action import Action
from aegis.guard.registry import ActionTypeRegistry

CONTEXT_KEY = "ddic_context"
"""Reserved key in ``Action.context`` carrying the DDIC application
context. Domains that need to express "the action happens in context X"
populate this field. Default ``Top`` is universal."""

TIME_KEY = "ddic_time"
"""Reserved key in ``Action.context`` carrying the DDIC query time.
Defaults to the canonical ``tn`` (now) symbol used by MELD rule defaults."""

DEFAULT_CONTEXT: DDICTerm = DDICSymbol("Top")
DEFAULT_TIME: DDICTerm = DDICSymbol("tn")


def action_behavior(action: Action, registry: ActionTypeRegistry) -> DDICTerm:
    """Map an action to its DDIC behavior term.

    With schema parameters → ``DDICCompound(head=action_type, args=...)``.
    Without parameters → ``DDICSymbol(action_type)``.
    """
    schema = registry.get_schema(action.action_type)
    if schema is None or not schema.parameters:
        return DDICSymbol(action.action_type)
    args: list[DDICTerm] = []
    for param in schema.parameters:
        if param.name in action.proposition:
            args.append(_term_from_value(action.proposition[param.name]))
    if not args:
        return DDICSymbol(action.action_type)
    return DDICCompound(head=action.action_type, args=tuple(args))


def action_context(action: Action) -> DDICTerm:
    """Map an action to its DDIC context term.

    Reads ``Action.context[CONTEXT_KEY]``; defaults to ``DEFAULT_CONTEXT``
    (``Top``).
    """
    raw = action.context.get(CONTEXT_KEY)
    if raw is None:
        return DEFAULT_CONTEXT
    return _term_from_value(raw)


def action_time(action: Action) -> DDICTerm:
    """Map an action to its DDIC query time term.

    Reads ``Action.context[TIME_KEY]``; defaults to ``DEFAULT_TIME``
    (``tn``). Domains that operate on Lex Posterior or scheduled
    obligations populate this field; for purely time-agnostic domains the
    default is sufficient.
    """
    raw = action.context.get(TIME_KEY)
    if raw is None:
        return DEFAULT_TIME
    return _term_from_value(raw)


def _term_from_value(value: object) -> DDICTerm:
    """Lift a Python value into a DDIC term.

    - ``int`` → ``DDICInteger``
    - non-empty ``tuple``/``list`` with string head → ``DDICCompound``
      (head is the first element, tail are recursively lifted args)
    - ``str`` (or anything else with ``__str__``) → ``DDICSymbol``

    The compound branch lets domains express richer behavior values
    inside a single proposition slot, e.g. ``("forwarded", "doc-42")``.
    """
    if isinstance(value, bool):
        return DDICSymbol(str(value))
    if isinstance(value, int):
        return DDICInteger(value)
    if isinstance(value, (tuple, list)) and value:
        head = value[0]
        if not isinstance(head, str):
            raise ValueError(f"Compound term head must be a string: {value!r}")
        return DDICCompound(
            head=head,
            args=tuple(_term_from_value(item) for item in value[1:]),
        )
    return DDICSymbol(str(value))
