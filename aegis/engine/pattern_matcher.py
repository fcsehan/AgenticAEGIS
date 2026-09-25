# Python adaptation for AEGIS; see THIRD_PARTY_NOTICES.md.
# Copyright (c) 1986-1993 Kenneth D. Forbus, Johan de Kleer and Xerox
# Corporation.  All Rights Reserved.
#
# Use, reproduction, and preparation of derivative works are permitted.
# Any copy of this software or of any derivative work must include the
# above copyright notice and this paragraph.  Any distribution of this
# software or derivative works must comply with all applicable United
# States export control laws.  This software is made available as is, and
# Kenneth D. Forbus, Johan de Kleer and Xerox Corporation disclaim all
# warranties, express or implied, including without limitation the implied
# warranties of merchantability and fitness for a particular purpose, and
# notwithstanding any other provision contained herein, any liability for
# damages resulting from the software or its use is expressly disclaimed,
# whether arising in contract, tort (including negligence) or strict
# liability, even if Kenneth D. Forbus, Johan de Kleer or Xerox
# Corporation is advised of the possibility of such damages.

"""Pattern matching via unification — port of BPS/ftre/unify.lisp.

Variables are strings starting with ``?`` (e.g. ``"?x"``).
Terms are tuples (compound) or strings (atoms/variables).
Bindings are dicts mapping variable names to their bound values.

The sentinel ``FAIL`` signals unification failure.
"""

from __future__ import annotations

from typing import Any

# Sentinel for failed unification — distinct from any valid binding.
FAIL: object = object()

# Type aliases for clarity.
Term = Any  # str | tuple[Any, ...] | int
Bindings = dict[str, Term]


def is_variable(x: Any) -> bool:
    """Return True if *x* is a logic variable (string starting with ``?``)."""
    return isinstance(x, str) and len(x) > 1 and x[0] == "?"


def unify(a: Term, b: Term, bindings: Bindings | None = None) -> Bindings | object:
    """Unify terms *a* and *b* under *bindings*.

    Returns extended bindings on success, or ``FAIL`` on failure.
    Port of ``unify`` in unify.lisp lines 20-29.
    """
    if bindings is None:
        bindings = {}

    if a == b:
        return bindings
    if is_variable(a):
        return _unify_variable(a, b, bindings)
    if is_variable(b):
        return _unify_variable(b, a, bindings)
    if not isinstance(a, tuple) or not isinstance(b, tuple):
        return FAIL
    if len(a) != len(b):
        return FAIL

    for x, y in zip(a, b, strict=True):
        result = unify(x, y, bindings)
        if result is FAIL:
            return FAIL
        bindings = result  # type: ignore[assignment]
    return bindings


def _unify_variable(var: str, exp: Term, bindings: Bindings) -> Bindings | object:
    """Unify a variable with an expression.

    Port of ``unify-variable`` in unify.lisp lines 31-38.
    """
    if var in bindings:
        return unify(bindings[var], exp, bindings)
    if not occurs_in(var, exp, bindings):
        new_bindings = dict(bindings)
        new_bindings[var] = exp
        return new_bindings
    return FAIL


def occurs_in(var: str, exp: Term, bindings: Bindings) -> bool:
    """Return True if *var* occurs in *exp* (occurs check).

    Port of ``free-in?`` in unify.lisp lines 40-52 (inverted logic —
    ``free-in?`` returns True when var does NOT occur, we return True when it does).
    """
    if exp is None:
        return False
    if var == exp:
        return True
    if is_variable(exp):
        if exp in bindings:
            return occurs_in(var, bindings[exp], bindings)
        return False
    if isinstance(exp, tuple):
        return any(occurs_in(var, element, bindings) for element in exp)
    return False


def sublis(bindings: Bindings, term: Term) -> Term:
    """Substitute all bound variables in *term* with their values.

    Recursively walks the term, replacing variables with their bindings.
    """
    if is_variable(term):
        if term in bindings:
            return sublis(bindings, bindings[term])
        return term
    if isinstance(term, tuple):
        return tuple(sublis(bindings, element) for element in term)
    return term


# ── DDICTerm unification ────────────────────────────────────────────
#
# Works on typed DDIC IR terms (DDICSymbol, DDICCompound, DDICVar, DDICInteger)
# instead of raw tuples.  Provides the same semantics as unify() above plus
# prefix-matching for Compounds with fewer args.


def unify_terms(
    a: object,
    b: object,
    bindings: dict[str, object] | None = None,
    *,
    prefix: bool = False,
) -> dict[str, object] | object:
    """Unify two DDIC terms.

    Returns bindings dict on success, ``FAIL`` on failure.

    When *prefix* is True, a DDICCompound with fewer args may match one with
    more args (matching only the leading args).  This mirrors the v1 prefix
    semantics of ``DDICEngine._proposition_matches()``.
    """
    from aegis.engine.ddic_ir import DDICCompound, DDICInteger, DDICSymbol, DDICVar

    if bindings is None:
        bindings = {}

    # Identity
    if a == b:
        return bindings

    # Variable binding
    if isinstance(a, DDICVar):
        return _unify_term_variable(a.name, b, bindings)
    if isinstance(b, DDICVar):
        return _unify_term_variable(b.name, a, bindings)

    # Symbol × Symbol
    if isinstance(a, DDICSymbol) and isinstance(b, DDICSymbol):
        return bindings if a.value == b.value else FAIL

    # Integer × Integer
    if isinstance(a, DDICInteger) and isinstance(b, DDICInteger):
        return bindings if a.value == b.value else FAIL

    # Compound × Compound
    if isinstance(a, DDICCompound) and isinstance(b, DDICCompound):
        if a.head != b.head:
            return FAIL
        a_args = a.args
        b_args = b.args
        if prefix and len(a_args) < len(b_args):
            b_args = b_args[: len(a_args)]
        elif prefix and len(b_args) < len(a_args):
            a_args = a_args[: len(b_args)]
        elif len(a_args) != len(b_args):
            return FAIL
        for x, y in zip(a_args, b_args, strict=True):
            result = unify_terms(x, y, bindings, prefix=prefix)
            if result is FAIL:
                return FAIL
            bindings = result  # type: ignore[assignment]
        return bindings

    # Symbol × Compound with prefix=True: Symbol acts as head-only match
    if prefix:
        if isinstance(a, DDICSymbol) and isinstance(b, DDICCompound):
            return bindings if a.value == b.head else FAIL
        if isinstance(b, DDICSymbol) and isinstance(a, DDICCompound):
            return bindings if b.value == a.head else FAIL

    return FAIL


def _unify_term_variable(
    var_name: str,
    exp: object,
    bindings: dict[str, object],
) -> dict[str, object] | object:
    """Bind a DDIC variable or check consistency with existing binding."""
    if var_name in bindings:
        return unify_terms(bindings[var_name], exp, bindings)
    new_bindings = dict(bindings)
    new_bindings[var_name] = exp
    return new_bindings


def proposition_to_term(proposition: tuple[object, ...]) -> object:
    """Convert a v1 proposition tuple to a DDICTerm.

    Single-element → DDICSymbol.
    Multi-element → DDICCompound(head, args...).
    """
    from aegis.engine.ddic_ir import DDICCompound, DDICSymbol

    if len(proposition) == 1:
        return DDICSymbol(str(proposition[0]))
    head = str(proposition[0])
    args = tuple(DDICSymbol(str(arg)) for arg in proposition[1:])
    return DDICCompound(head=head, args=args)


def fetch(pattern: Term, facts: list[Term]) -> list[Term]:
    """Find all facts that unify with *pattern*, returning substituted results.

    Port of ``fetch`` in fdata.lisp lines 89-95.
    Returns a list of ground terms where each is the pattern with variables
    replaced by the values from unification.
    """
    results: list[Term] = []
    for candidate in facts:
        result = unify(pattern, candidate)
        if result is not FAIL:
            results.append(sublis(result, pattern))  # type: ignore[arg-type]
    return results
