"""Tests for InheritanceGraph."""

from __future__ import annotations

from aegis.engine.inheritance import InheritanceGraph
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


def _build_graph() -> InheritanceGraph:
    kb = KnowledgeBase()
    kb.create_mt("test")
    kb.assert_fact(("genls", "Labrador", "Dog"), "test")
    kb.assert_fact(("genls", "Dog", "Animal"), "test")
    kb.assert_fact(("genls", "Animal", "LivingThing"), "test")
    kb.assert_fact(("isa", "Rex", "Labrador"), "test")
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return InheritanceGraph(reasoner)


class TestInheritanceGraph:
    def test_specificity(self) -> None:
        g = _build_graph()
        assert g.specificity_of("Labrador") > g.specificity_of("Dog")
        assert g.specificity_of("Dog") > g.specificity_of("Animal")

    def test_is_subtype(self) -> None:
        g = _build_graph()
        assert g.is_subtype("Labrador", "Dog")
        assert g.is_subtype("Dog", "Animal")
        assert g.is_subtype("Labrador", "Animal")
        assert not g.is_subtype("Animal", "Dog")

    def test_is_instance(self) -> None:
        g = _build_graph()
        assert g.is_instance("Rex", "Labrador")
        # Transitive: Rex isa Labrador, Labrador genls Dog → Rex isa Dog
        assert g.is_instance("Rex", "Dog")
