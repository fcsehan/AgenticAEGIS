"""Tests for Microtheory."""

from __future__ import annotations

from aegis.kb.microtheory import Microtheory


class TestMicrotheory:
    def test_assert_fact(self) -> None:
        mt = Microtheory(name="TestMt")
        assert mt.assert_fact(("isa", "Dog", "Animal")) is True
        assert mt.assert_fact(("isa", "Dog", "Animal")) is False  # idempotent

    def test_query_local(self) -> None:
        mt = Microtheory(name="TestMt")
        mt.assert_fact(("isa", "Dog", "Animal"))
        mt.assert_fact(("genls", "Dog", "Animal"))
        results = mt.query_local("isa")
        assert len(results) == 1
        assert results[0] == ("isa", "Dog", "Animal")

    def test_query_inherits_from_parent(self) -> None:
        parent = Microtheory(name="ParentMt")
        parent.assert_fact(("isa", "Animal", "LivingThing"))
        child = Microtheory(name="ChildMt", parent=parent)
        child.assert_fact(("isa", "Dog", "Animal"))

        results = child.query("isa")
        assert len(results) == 2

    def test_chain(self) -> None:
        root = Microtheory(name="Root")
        mid = Microtheory(name="Mid", parent=root)
        leaf = Microtheory(name="Leaf", parent=mid)
        chain = list(leaf.chain())
        assert [m.name for m in chain] == ["Leaf", "Mid", "Root"]
