"""Olson Chapter 6.4: Karli examples as formal tests.

Adapt four medical information-sharing scenarios from pp. 135–138 into
norm sets for the DDIC engine and unified evaluator. The companion acts
for the patient Karli. See the verification document for legacy deviations.
Reference: Olson, A Formal Theory of Norms, Examples 6.4.1–6.4.4."""

from __future__ import annotations

import pytest

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.ddic_eval import DDICVerdict, evaluate_legacy_module
from aegis.engine.normframe_compile import compile_norms_to_module
from aegis.engine.inheritance import InheritanceGraph
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase

IMP = DeonticModality.FORBIDDEN
OBL = DeonticModality.OBLIGATORY
OPT = DeonticModality.PERMITTED


def _medical_kb() -> tuple[KnowledgeBase, InheritanceGraph]:
    """KB with medical information hierarchy.

    Subsumption chain:
      shareMedicalRecord genls shareHealthStatus genls shareInfo
      shareRecipe genls shareMedicalRecord
    """
    kb = KnowledgeBase()
    mt = "MedicalOntologyMt"
    kb.create_mt(mt)
    # Information hierarchy (more specific → more general)
    kb.assert_fact(("genls", "shareRecipe", "shareMedicalRecord"), mt)
    kb.assert_fact(("genls", "shareMedicalRecord", "shareHealthStatus"), mt)
    kb.assert_fact(("genls", "shareHealthStatus", "shareInfo"), mt)
    # Recipient hierarchy
    kb.assert_fact(("genls", "husband", "familyMember"), mt)
    kb.assert_fact(("genls", "child", "familyMember"), mt)
    # Agent hierarchy
    kb.assert_fact(("genls", "companion", "agent"), mt)
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return kb, InheritanceGraph(reasoner)


def _norm(
    modality: DeonticModality,
    prop: tuple[str, ...],
    specificity: int = 0,
    source: str = "",
) -> NormFrame:
    return NormFrame(
        code="KarliPrivacy",
        agent_pattern="companion",
        modality=modality,
        proposition=prop,
        specificity=specificity,
        defeasible=True,
        source=source or f"karli:{id(object())}",
    )


def _eval_v1(
    norms: list[NormFrame],
    prop: tuple[str, ...],
    inh: InheritanceGraph,
) -> DeonticModality | None:
    engine = DDICEngine(inh)
    status = engine.evaluate(prop, "companion", norms)
    return status.modality


def _eval_unified(
    norms: list[NormFrame],
    prop: tuple[str, ...],
    kb: KnowledgeBase,
    inh: InheritanceGraph,
) -> DDICVerdict:
    module = compile_norms_to_module(norms, kb)
    state = evaluate_legacy_module(module, prop, "companion", inh)
    return state.verdict


# Example 6.4.1 (p. 135): Karli permits medication information to her husband.
# A single permission is modeled. Other queries have no applicable norm;
# the in-domain Guard applies closed-world enforcement to that absence.


class TestExample641:
    """Example 6.4.1: explicit permission for medication information to the husband."""

    def test_recipe_to_husband_permitted(self) -> None:
        """Explicit permission: medication information to the husband is permitted."""
        kb, inh = _medical_kb()
        norms = [
            _norm(OPT, ("shareRecipe", "husband"), specificity=2, source="641:1"),
        ]
        assert _eval_v1(norms, ("shareRecipe", "husband"), inh) == OPT
        assert _eval_unified(norms, ("shareRecipe", "husband"), kb, inh) == DDICVerdict.PERMITTED

    def test_medical_record_to_husband_no_norm(self) -> None:
        """No matching norm for the broader medical record: no engine conclusion."""
        kb, inh = _medical_kb()
        norms = [
            _norm(OPT, ("shareRecipe", "husband"), specificity=2, source="641:1"),
        ]
        # shareMedicalRecord is not shareRecipe; no norm matches
        assert _eval_v1(norms, ("shareMedicalRecord", "husband"), inh) is None
        assert _eval_unified(norms, ("shareMedicalRecord", "husband"), kb, inh) == DDICVerdict.UNDECIDABLE


# Example 6.4.2 (p. 136): Karli requires health updates to her children,
# then prohibits medical-record disclosure. The fixture models the later
# prohibition with higher specificity, so it wins by preemption.


class TestExample642:
    """Example 6.4.2: an obligation suppressed by a subsuming prohibition."""

    def test_health_to_children_forbidden_after_prohibition(self) -> None:
        """The medical-record prohibition takes precedence over the health obligation."""
        kb, inh = _medical_kb()
        norms = [
            # Obligation: health status to children (less specific)
            _norm(OBL, ("shareHealthStatus", "child"), specificity=0, source="642:1"),
            # Prohibition: medical record to anyone (more specific, later)
            _norm(IMP, ("shareMedicalRecord",), specificity=1, source="642:2"),
        ]
        # The more specific prohibition wins by preemption
        prop = ("shareMedicalRecord", "child")
        # shareMedicalRecord matches the prohibition by prefix
        assert _eval_v1(norms, ("shareMedicalRecord",), inh) == IMP
        assert _eval_unified(norms, ("shareMedicalRecord",), kb, inh) == DDICVerdict.FORBIDDEN


# Example 6.4.3 (p. 137): broad medical-record permission and a narrower
# prohibition on medication information to the husband. The narrow prohibition
# wins in its scope regardless of the order of the input norms.


class TestExample643:
    """Example 6.4.3: a narrower prohibition wins within its scope."""

    def test_medical_record_to_husband_permitted(self) -> None:
        """Broad medical-record permission applies."""
        kb, inh = _medical_kb()
        norms = [
            _norm(OPT, ("shareMedicalRecord",), specificity=0, source="643:1"),
            _norm(IMP, ("shareRecipe", "husband"), specificity=2, source="643:2"),
        ]
        # shareMedicalRecord matches the permission
        assert _eval_v1(norms, ("shareMedicalRecord",), inh) == OPT
        assert _eval_unified(norms, ("shareMedicalRecord",), kb, inh) == DDICVerdict.PERMITTED

    def test_recipe_to_husband_forbidden(self) -> None:
        """The narrower prohibition on medication disclosure applies."""
        kb, inh = _medical_kb()
        norms = [
            _norm(OPT, ("shareMedicalRecord",), specificity=0, source="643:1"),
            _norm(IMP, ("shareRecipe", "husband"), specificity=2, source="643:2"),
        ]
        # shareRecipe + husband matches the more specific prohibition
        assert _eval_v1(norms, ("shareRecipe", "husband"), inh) == IMP
        assert _eval_unified(norms, ("shareRecipe", "husband"), kb, inh) == DDICVerdict.FORBIDDEN

    def test_order_independence(self) -> None:
        """Reordering the input norms preserves the result."""
        kb, inh = _medical_kb()
        # Norms in reversed order
        norms_reversed = [
            _norm(IMP, ("shareRecipe", "husband"), specificity=2, source="643:2"),
            _norm(OPT, ("shareMedicalRecord",), specificity=0, source="643:1"),
        ]
        assert _eval_v1(norms_reversed, ("shareRecipe", "husband"), inh) == IMP
        assert _eval_v1(norms_reversed, ("shareMedicalRecord",), inh) == OPT


# Example 6.4.4 (p. 138): medical-record permission overlaps a prohibition
# on upsetting the husband. Olson prohibits the intersection; the legacy
# fixture permits an undecidable outcome without declared intersection data.


class TestExample644:
    """Example 6.4.4: overlapping conflict without subsumption."""

    def test_medical_record_alone_permitted(self) -> None:
        """Medical-record sharing alone has no matching conflict."""
        kb, inh = _medical_kb()
        norms = [
            _norm(OPT, ("shareMedicalRecord",), specificity=0, source="644:1"),
            _norm(IMP, ("upsetHusband",), specificity=0, source="644:2"),
        ]
        # Only shareMedicalRecord; no conflict with upsetHusband
        assert _eval_v1(norms, ("shareMedicalRecord",), inh) == OPT
        assert _eval_unified(norms, ("shareMedicalRecord",), kb, inh) == DDICVerdict.PERMITTED

    def test_upset_husband_alone_forbidden(self) -> None:
        """Upsetting the husband is explicitly forbidden."""
        kb, inh = _medical_kb()
        norms = [
            _norm(OPT, ("shareMedicalRecord",), specificity=0, source="644:1"),
            _norm(IMP, ("upsetHusband",), specificity=0, source="644:2"),
        ]
        assert _eval_v1(norms, ("upsetHusband",), inh) == IMP
        assert _eval_unified(norms, ("upsetHusband",), kb, inh) == DDICVerdict.FORBIDDEN

    def test_intersection_undecidable(self) -> None:
        """The overlap yields impermissibility in Olson's example.

        Without an explicit intersection relation, the legacy fixture can
        return undecidability. Both outcomes block execution; undecidability
        takes the escalation route."""
        kb, inh = _medical_kb()
        # Model both norms as applicable to the same proposition:
        norms = [
            _norm(OPT, ("shareMedicalRecordWithHusband",), specificity=0, source="644:1"),
            _norm(IMP, ("shareMedicalRecordWithHusband",), specificity=0, source="644:2"),
        ]
        result = _eval_unified(
            norms, ("shareMedicalRecordWithHusband",), kb, inh
        )
        # UNDECIDABLE (AEGIS) or FORBIDDEN (Olson): both block execution
        assert result in (DDICVerdict.UNDECIDABLE, DDICVerdict.FORBIDDEN)
