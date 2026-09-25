"""Tests for FactIndex."""

from __future__ import annotations

from aegis.kb.indexing import FactIndex


class TestFactIndex:
    def test_assert_and_query(self) -> None:
        idx = FactIndex()
        idx.assert_fact(("isa", "Dog", "Animal"), "TestMt")
        results = idx.query(("isa", "?x", "Animal"))
        assert len(results) == 1
        assert ("isa", "Dog", "Animal") in results

    def test_idempotent(self) -> None:
        idx = FactIndex()
        assert idx.assert_fact(("isa", "Dog", "Animal"), "TestMt") is True
        assert idx.assert_fact(("isa", "Dog", "Animal"), "TestMt") is False

    def test_query_mt(self) -> None:
        idx = FactIndex()
        idx.assert_fact(("isa", "Dog", "Animal"), "Mt1")
        idx.assert_fact(("isa", "Cat", "Animal"), "Mt2")
        results = idx.query_mt(("isa", "?x", "Animal"), "Mt1")
        assert len(results) == 1
        assert ("isa", "Dog", "Animal") in results

    def test_facts_in_mt(self) -> None:
        idx = FactIndex()
        idx.assert_fact(("isa", "Dog", "Animal"), "Mt1")
        idx.assert_fact(("genls", "Dog", "Animal"), "Mt1")
        idx.assert_fact(("isa", "Cat", "Animal"), "Mt2")
        facts = idx.facts_in_mt("Mt1")
        assert len(facts) == 2
