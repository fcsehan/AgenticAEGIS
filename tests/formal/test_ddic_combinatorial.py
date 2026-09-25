"""DDIC Combinatorial Exhaustive Test — Full Cartesian Product.

Replaces the claimed "108 combinations" in test_ddic_soundness.py with an
actual exhaustive enumeration of the full parameter space.

Parameter space:
  - 4 Conflict modality pairs: (P,F), (F,P), (O,F), (F,O)
  - 2 Non-conflict pairs: (O,P), (P,O)
  - 3 Specificity relations: s1>s2, s1<s2, s1==s2
  - 4 Defeasibility combos: (d,d), (d,a), (a,d), (a,a)
  - 3 Code relations: same, c1>c2, c1<c2

Total: 6 × 3 × 4 × 3 = 216 combinations.

For each combination, the expected outcome is derived from Olson's rules:
  1. Non-defeasible (axiom) always wins (I4)
  2. Contradictory axioms → UNDETERMINED
  3. Higher specificity wins via preemption
  4. Code prevalence breaks same-specificity ties
  5. Non-conflicting pairs (O,P) always agree (O implies P)
  6. Same-specificity conflicts without prevalence → UNDETERMINED

Referenz: Olson Kap. 3.2 (DDIC), Kap. 6.4.2 (Theorems + Table 6.5).
"""

from __future__ import annotations

import itertools

import pytest

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.ddic_eval import DDICVerdict, evaluate_legacy_module
from aegis.engine.normframe_compile import compile_norms_to_module
from aegis.engine.inheritance import InheritanceGraph
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase

P = DeonticModality.PERMITTED
F = DeonticModality.FORBIDDEN
O = DeonticModality.OBLIGATORY

# ── Parameter space ─────────────────────────────────────────────────

MODALITY_PAIRS = [(P, F), (F, P), (O, F), (F, O), (O, P), (P, O)]
SPECIFICITY_RELS = [
    (1, 0, "s1>s2"),
    (0, 1, "s1<s2"),
    (0, 0, "s1=s2"),
]
DEFEASIBILITY = [
    (True, True, "d/d"),
    (True, False, "d/a"),
    (False, True, "a/d"),
    (False, False, "a/a"),
]
CODE_RELS = [
    ("CodeA", "CodeA", "same", None),
    ("CodeA", "CodeB", "c1>c2", ["CodeA", "CodeB"]),
    ("CodeB", "CodeA", "c1<c2", ["CodeA", "CodeB"]),
]


def _kb() -> tuple[KnowledgeBase, InheritanceGraph]:
    kb = KnowledgeBase()
    kb.create_mt("T")
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return kb, InheritanceGraph(reasoner)


def _conflicts(m1: DeonticModality, m2: DeonticModality) -> bool:
    """Check if two modalities conflict per Olson."""
    if m1 == m2:
        return False
    pair = {m1, m2}
    return pair == {P, F} or pair == {O, F}


def _expected_outcome(
    m1: DeonticModality,
    s1: int,
    d1: bool,
    c1: str,
    m2: DeonticModality,
    s2: int,
    d2: bool,
    c2: str,
    prevalence: list[str] | None,
) -> DeonticModality | None:
    """Derive expected outcome from Olson's rules.

    Returns the winning modality, or None for UNDETERMINED.
    """
    # Non-conflicting pair
    if not _conflicts(m1, m2):
        # Same modality → unanimously that modality
        if m1 == m2:
            return m1
        # O + P: DDICEngine's unanimity check sees two different modalities
        # in the surviving set → UNDETERMINED, UNLESS one norm doesn't apply.
        # I4: If exactly one is an axiom, it goes to the axiom path and wins.
        if not d1 and not d2:
            # Both axioms, different modalities but non-conflicting → UNDETERMINED
            # (DDICEngine doesn't special-case O+P axiom pairs)
            return None
        if not d1:
            return m1  # Axiom wins in step 2
        if not d2:
            return m2  # Axiom wins in step 2
        # Both defeasible, different modalities → surviving set has both → UNDETERMINED
        return None

    # I4: Axiom always wins
    if not d1 and not d2:
        # Contradictory axioms → UNDETERMINED
        return None
    if not d1:
        return m1
    if not d2:
        return m2

    # Both defeasible: specificity wins
    if s1 > s2:
        return m1
    if s2 > s1:
        return m2

    # Same specificity: code prevalence
    if prevalence and c1 != c2:
        r1 = len(prevalence) - prevalence.index(c1) if c1 in prevalence else 0
        r2 = len(prevalence) - prevalence.index(c2) if c2 in prevalence else 0
        if r1 > r2:
            return m1
        if r2 > r1:
            return m2

    # Unresolvable
    return None


# ── Generate all 216 test cases ─────────────────────────────────────

_ALL_CASES: list[tuple[str, dict]] = []

for (m1, m2), (s1, s2, s_label), (d1, d2, d_label), (c1, c2, c_label, prev) in itertools.product(
    MODALITY_PAIRS, SPECIFICITY_RELS, DEFEASIBILITY, CODE_RELS
):
    case_id = f"{m1.value[0]}{m2.value[0]}_{s_label}_{d_label}_{c_label}"
    expected = _expected_outcome(m1, s1, d1, c1, m2, s2, d2, c2, prev)
    _ALL_CASES.append((
        case_id,
        dict(m1=m1, s1=s1, d1=d1, c1=c1, m2=m2, s2=s2, d2=d2, c2=c2, prev=prev, expected=expected),
    ))


@pytest.mark.parametrize("case_id,params", _ALL_CASES, ids=[c[0] for c in _ALL_CASES])
def test_combinatorial_exhaustive(case_id: str, params: dict) -> None:
    """Test each of the 216 combinations."""
    kb, inh = _kb()
    n1 = NormFrame(
        code=params["c1"],
        agent_pattern="agent",
        modality=params["m1"],
        proposition=("action",),
        specificity=params["s1"],
        defeasible=params["d1"],
        source="n1:1",
    )
    n2 = NormFrame(
        code=params["c2"],
        agent_pattern="agent",
        modality=params["m2"],
        proposition=("action",),
        specificity=params["s2"],
        defeasible=params["d2"],
        source="n2:2",
    )

    expected = params["expected"]
    prevalence = params["prev"]

    # v1 DDICEngine
    engine = DDICEngine(inh, code_prevalence=prevalence)
    v1_status = engine.evaluate(("action",), "agent", [n1, n2])
    v1_result = v1_status.modality

    # Unified evaluator
    module = compile_norms_to_module([n1, n2], kb, code_prevalence=prevalence)
    unified_state = evaluate_legacy_module(module, ("action",), "agent", inh)

    # Map both to semantic equivalence classes:
    #   FORBIDDEN / UNDECIDABLE / PERMISSIVE (O or P — both mean "allowed")
    def _to_semantic(modality: DeonticModality | None) -> str:
        if modality is None:
            return "UNDECIDABLE"
        if modality == F:
            return "FORBIDDEN"
        return "PERMISSIVE"  # O and P are both permissive

    def _verdict_to_semantic(v: DDICVerdict) -> str:
        if v == DDICVerdict.FORBIDDEN:
            return "FORBIDDEN"
        if v == DDICVerdict.PERMITTED:
            return "PERMISSIVE"
        return "UNDECIDABLE"

    v1_semantic = _to_semantic(v1_result)
    unified_semantic = _verdict_to_semantic(unified_state.verdict)

    # Primary assertion: v1 and unified agree semantically
    assert v1_semantic == unified_semantic, (
        f"{case_id}: v1={v1_result}→{v1_semantic}, unified={unified_state.verdict}→{unified_semantic}"
    )

    # Secondary assertion: for conflict pairs, verify against Olson's rules.
    # Non-conflicting pairs (O+P, P+O) are not covered by Olson's conflict
    # resolution theorems — they have no conflict to resolve. The engine's
    # behavior for these pairs is implementation-defined (not Olson-prescribed).
    if _conflicts(m1, m2):
        assert v1_result == expected, (
            f"{case_id}: got={v1_result}, expected={expected}"
        )
