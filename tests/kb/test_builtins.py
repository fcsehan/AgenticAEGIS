"""Tests for BuiltinEngine (transitive closures)."""

from __future__ import annotations

import pytest

from aegis.errors import InheritanceCycleError
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


def _make_reasoner(facts: list[tuple[object, ...]]) -> BuiltinEngine:
    kb = KnowledgeBase()
    kb.create_mt("test")
    for fact in facts:
        kb.assert_fact(fact, "test")
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    return reasoner


class TestBuiltinEngine:
    def test_isa_direct(self) -> None:
        r = _make_reasoner([("isa", "Rex", "Dog")])
        assert r.is_isa("Rex", "Dog")

    def test_isa_transitive_via_genls(self) -> None:
        r = _make_reasoner(
            [
                ("isa", "Rex", "Dog"),
                ("genls", "Dog", "Animal"),
            ]
        )
        assert r.is_isa("Rex", "Dog")
        assert r.is_isa("Rex", "Animal")

    def test_genls_transitive(self) -> None:
        r = _make_reasoner(
            [
                ("genls", "Labrador", "Dog"),
                ("genls", "Dog", "Animal"),
                ("genls", "Animal", "LivingThing"),
            ]
        )
        assert r.is_genls("Labrador", "Animal")
        assert r.is_genls("Labrador", "LivingThing")
        assert not r.is_genls("Animal", "Dog")

    def test_genl_preds(self) -> None:
        r = _make_reasoner([("genlPreds", "sub", "sup")])
        assert r.is_genl_pred("sub", "sup")
        assert not r.is_genl_pred("sup", "sub")

    def test_negation_preds(self) -> None:
        r = _make_reasoner([("negationPreds", "a", "b")])
        assert r.are_negation_preds("a", "b")
        assert r.are_negation_preds("b", "a")  # symmetric

    def test_cycle_detection(self) -> None:
        with pytest.raises(InheritanceCycleError):
            _make_reasoner(
                [
                    ("genls", "A", "B"),
                    ("genls", "B", "A"),
                ]
            )

    def test_depth_of(self) -> None:
        r = _make_reasoner(
            [
                ("genls", "Labrador", "Dog"),
                ("genls", "Dog", "Animal"),
            ]
        )
        assert r.depth_of("Labrador") > r.depth_of("Dog")
        assert r.depth_of("Dog") > 0
