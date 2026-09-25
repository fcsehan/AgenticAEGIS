"""AEGIS-1105: Olson DDIC Dissertation Test Suite.

Implements canonical examples from:
  - Olson, "Defeasible Deontic Inheritance Calculus" (AAAI 2025)
  - arXiv:2407.04869

Each test documents the example number from the source material.
These tests validate that the DDIC engine correctly implements
the core defeasible deontic reasoning patterns.
"""

from __future__ import annotations

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.inheritance import InheritanceGraph
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase

F = DeonticModality.FORBIDDEN
P = DeonticModality.PERMITTED
OB = DeonticModality.OBLIGATORY


def _graph_with_hierarchy(*genls_pairs: tuple[str, str]) -> InheritanceGraph:
    """Build an InheritanceGraph with the given genls relationships."""
    kb = KnowledgeBase()
    mt = kb.create_mt("test")
    for sub, sup in genls_pairs:
        kb.assert_fact(("genls", sub, sup), mt)
        kb.assert_fact(("isa", sub, sup), mt)
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return InheritanceGraph(reasoner)


def _simple_graph() -> InheritanceGraph:
    kb = KnowledgeBase()
    kb.create_mt("test")
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return InheritanceGraph(reasoner)


def _norm(
    modality: DeonticModality,
    agent: str = "*",
    code: str = "C",
    specificity: int = 0,
    defeasible: bool = True,
    proposition: tuple[object, ...] = ("action",),
    source: str = "",
) -> NormFrame:
    return NormFrame(
        code=code,
        agent_pattern=agent,
        modality=modality,
        proposition=proposition,
        specificity=specificity,
        defeasible=defeasible,
        source=source,
    )


# ── Olson Example 1: Permissive Inheritance ────────────────────
# General norm: FORBIDDEN for category C.
# Specific norm: PERMITTED for subcategory S ⊂ C.
# Result: S → PERMITTED (specific overrides general).


class TestPermissiveInheritance:
    """Olson §3.1: Permissive inheritance.

    A general prohibition can be overridden by a more specific permission.
    This is the core defeasibility pattern.
    """

    def test_specific_permission_overrides_general_prohibition(self) -> None:
        """General FORBIDDEN at specificity=0, specific PERMITTED at specificity=2."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", specificity=0, source="general-forbid"),
            _norm(P, agent="a", specificity=2, source="specific-permit"),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_permitted()
        assert status.reason == "specificity"
        assert len(status.defeated_norms) == 1
        assert status.defeated_norms[0].source == "general-forbid"

    def test_specific_prohibition_overrides_general_permission(self) -> None:
        """The reverse: general PERMITTED, specific FORBIDDEN."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(P, agent="a", specificity=0, source="general-permit"),
            _norm(F, agent="a", specificity=2, source="specific-forbid"),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_forbidden()
        assert status.reason == "specificity"

    def test_three_level_inheritance(self) -> None:
        """Three levels: general FORBIDDEN → mid PERMITTED → specific FORBIDDEN again."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", specificity=0, source="L0-forbid"),
            _norm(P, agent="a", specificity=1, source="L1-permit"),
            _norm(F, agent="a", specificity=2, source="L2-forbid"),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_forbidden()
        assert status.reason == "specificity"
        # Most specific wins: L2
        assert any(n.source == "L2-forbid" for n in status.winning_norms)


# ── Olson Example 2: Preemption ────────────────────────────────
# Two norms at equal specificity conflict → need another mechanism
# to resolve (prevalence or UNDETERMINED).


class TestPreemption:
    """Olson §3.2: Preemption and equal-specificity conflicts.

    When two norms have equal specificity and conflict,
    specificity alone cannot resolve. Cross-code prevalence
    or UNDETERMINED results.
    """

    def test_equal_specificity_no_prevalence_undetermined(self) -> None:
        """Same code, same specificity → UNDETERMINED."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(P, agent="a", code="Same", specificity=1),
            _norm(F, agent="a", code="Same", specificity=1),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_undetermined()
        assert status.reason == "unresolved_conflict"

    def test_equal_specificity_prevalence_resolves(self) -> None:
        """Same specificity but different codes → prevalence resolves."""
        engine = DDICEngine(
            _simple_graph(),
            code_prevalence=["HighCode", "LowCode"],
        )
        norms = [
            _norm(P, agent="a", code="LowCode", specificity=1),
            _norm(F, agent="a", code="HighCode", specificity=1),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_forbidden()
        assert status.reason == "cross_code_prevalence"

    def test_preempted_norm_does_not_participate(self) -> None:
        """A preempted (defeated) norm should not affect the final result."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", specificity=0, source="low-forbid"),
            _norm(P, agent="a", specificity=2, source="high-permit"),
            # This norm is at specificity=1, between the two.
            # It conflicts with the high-permit but is less specific.
            _norm(F, agent="a", specificity=1, source="mid-forbid"),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_permitted()
        # Both lower norms should be defeated
        assert len(status.defeated_norms) >= 1


# ── Olson Example 3: Hierarchical Code Ordering ────────────────
# Multiple codes with prevalence ordering determine which
# norm wins when specificity is equal.


class TestHierarchicalCodes:
    """Olson §3.3: Hierarchical code ordering.

    When norms from different codes conflict at the same specificity,
    the code's position in the prevalence ordering determines the winner.
    """

    def test_three_codes_highest_wins(self) -> None:
        """Three codes: Emergency > Standard > Default."""
        engine = DDICEngine(
            _simple_graph(),
            code_prevalence=["Emergency", "Standard", "Default"],
        )
        norms = [
            _norm(F, agent="a", code="Default", specificity=0),
            _norm(F, agent="a", code="Standard", specificity=0),
            _norm(P, agent="a", code="Emergency", specificity=0),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_permitted()
        assert status.reason == "cross_code_prevalence"

    def test_prevalence_does_not_override_specificity(self) -> None:
        """Specificity takes priority over prevalence.

        Even if a lower-prevalence code has higher specificity, it wins.
        This is the Olson principle: specificity > prevalence.
        """
        engine = DDICEngine(
            _simple_graph(),
            code_prevalence=["HighCode", "LowCode"],
        )
        norms = [
            _norm(F, agent="a", code="HighCode", specificity=0),
            _norm(P, agent="a", code="LowCode", specificity=3),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_permitted()
        assert status.reason == "specificity"

    def test_no_prevalence_configured_undetermined(self) -> None:
        """If no prevalence is configured, equal-specificity conflicts → UNDETERMINED."""
        engine = DDICEngine(_simple_graph())  # no code_prevalence
        norms = [
            _norm(P, agent="a", code="A", specificity=0),
            _norm(F, agent="a", code="B", specificity=0),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_undetermined()


# ── Olson Example 4: Chained Inheritance ───────────────────────
# A → B → C hierarchy with defeasibility at each level.


class TestChainedInheritance:
    """Olson §3.4: Chained inheritance with defeasibility.

    Norms at different levels of a chain, where each more-specific
    level can defeat the less-specific one.
    """

    def test_chain_a_b_c_most_specific_wins(self) -> None:
        """A(s=0) → B(s=1) → C(s=2), conflicting modalities."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", specificity=0, source="A:FORBIDDEN"),
            _norm(P, agent="a", specificity=1, source="B:PERMITTED"),
            _norm(F, agent="a", specificity=2, source="C:FORBIDDEN"),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_forbidden()
        # C is most specific and wins
        assert any(n.source == "C:FORBIDDEN" for n in status.winning_norms)

    def test_chain_with_non_defeasible_at_root(self) -> None:
        """Moral axiom at root level wins over all specific norms."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", specificity=0, defeasible=False, source="axiom"),
            _norm(P, agent="a", specificity=5, source="very-specific"),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_forbidden()
        assert status.reason == "moral_axiom"

    def test_chain_all_agree(self) -> None:
        """When all levels agree on modality, no conflict."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", specificity=0),
            _norm(F, agent="a", specificity=1),
            _norm(F, agent="a", specificity=2),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_forbidden()


# ── Olson Example 5: Multiple Inheritance ──────────────────────
# A node inherits from two paths with potentially conflicting norms.


class TestMultipleInheritance:
    """Olson §3.5: Multiple inheritance.

    When an agent inherits norms from two independent paths,
    conflicts must be resolved by specificity or prevalence.
    """

    def test_two_paths_same_specificity_undetermined(self) -> None:
        """Two independent paths, same specificity, same code → UNDETERMINED."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(P, agent="a", code="Path1", specificity=1, source="path1-permit"),
            _norm(F, agent="a", code="Path2", specificity=1, source="path2-forbid"),
        ]
        # No prevalence → can't resolve
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_undetermined()

    def test_two_paths_prevalence_resolves(self) -> None:
        """Two paths, prevalence ordering resolves conflict."""
        engine = DDICEngine(
            _simple_graph(),
            code_prevalence=["Path1", "Path2"],
        )
        norms = [
            _norm(P, agent="a", code="Path1", specificity=1),
            _norm(F, agent="a", code="Path2", specificity=1),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_permitted()  # Path1 has higher prevalence

    def test_two_paths_one_more_specific(self) -> None:
        """Two paths, one more specific — specificity wins."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(P, agent="a", code="Path1", specificity=1),
            _norm(F, agent="a", code="Path2", specificity=3),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_forbidden()  # Path2 is more specific

    def test_diamond_inheritance(self) -> None:
        """Diamond pattern: A←B, A←C, B←D, C←D. D gets norms from B and C."""
        engine = DDICEngine(
            _simple_graph(),
            code_prevalence=["CodeB", "CodeC"],
        )
        norms = [
            _norm(P, agent="D", code="CodeB", specificity=2, source="via-B"),
            _norm(F, agent="D", code="CodeC", specificity=2, source="via-C"),
        ]
        status = engine.evaluate(("action",), "D", norms)
        # CodeB has higher prevalence → PERMITTED
        assert status.is_permitted()


# ── Olson: Contradictory Moral Axioms ──────────────────────────


class TestContradictoryAxioms:
    """Edge case: two moral axioms that contradict each other.

    This should never happen in a well-formed domain, but the engine
    must handle it gracefully (UNDETERMINED, not crash).
    """

    def test_contradictory_axioms_undetermined(self) -> None:
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(P, agent="a", defeasible=False),
            _norm(F, agent="a", defeasible=False),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_undetermined()
        assert status.reason == "contradictory_axioms"


# ── Olson: Proposition Matching ────────────────────────────────


class TestPropositionMatching:
    """Norms match based on proposition content, not just existence."""

    def test_different_propositions_no_conflict(self) -> None:
        """Norms for different propositions don't conflict."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", proposition=("share", "classified")),
            _norm(P, agent="a", proposition=("share", "unclassified")),
        ]
        # Evaluating "share classified" should only match the FORBIDDEN norm
        status = engine.evaluate(("share", "classified"), "a", norms)
        assert status.is_forbidden()

    def test_prefix_matching(self) -> None:
        """A norm with fewer proposition args matches longer propositions."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", proposition=("share",)),
        ]
        status = engine.evaluate(("share", "classified", "external"), "a", norms)
        assert status.is_forbidden()

    def test_no_matching_norms(self) -> None:
        """When no norms match the proposition → undetermined."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", proposition=("delete",)),
        ]
        status = engine.evaluate(("share", "classified"), "a", norms)
        assert status.is_undetermined()
        assert status.reason == "no_applicable_norms"


# ── Olson: Obligation Modality ─────────────────────────────────


class TestObligationModality:
    """OBLIGATORY norms and their interaction with FORBIDDEN/PERMITTED."""

    def test_obligation_stands_alone(self) -> None:
        engine = DDICEngine(_simple_graph())
        norms = [_norm(OB, agent="a")]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_obligatory()

    def test_obligation_vs_forbidden_specificity(self) -> None:
        """OBLIGATORY at higher specificity overrides FORBIDDEN."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", specificity=0),
            _norm(OB, agent="a", specificity=2),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_obligatory()

    def test_forbidden_vs_obligation_same_specificity(self) -> None:
        """OBLIGATORY vs FORBIDDEN at same specificity without prevalence → UNDETERMINED."""
        engine = DDICEngine(_simple_graph())
        norms = [
            _norm(F, agent="a", code="X", specificity=1),
            _norm(OB, agent="a", code="X", specificity=1),
        ]
        status = engine.evaluate(("action",), "a", norms)
        assert status.is_undetermined()
