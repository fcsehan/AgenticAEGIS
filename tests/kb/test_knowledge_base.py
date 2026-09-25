"""Tests for KnowledgeBase."""

from __future__ import annotations

import pytest

from aegis.kb.knowledge_base import KnowledgeBase


class TestKnowledgeBase:
    def test_create_mt(self) -> None:
        kb = KnowledgeBase()
        mt = kb.create_mt("TestMt")
        assert mt.name == "TestMt"
        assert "TestMt" in kb.microtheories

    def test_create_mt_with_parent(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("Parent")
        kb.create_mt("Child", parent="Parent")
        child = kb.get_mt("Child")
        assert child is not None
        assert child.parent is not None
        assert child.parent.name == "Parent"

    def test_create_mt_missing_parent_raises(self) -> None:
        kb = KnowledgeBase()
        with pytest.raises(ValueError, match="Parent microtheory not found"):
            kb.create_mt("Child", parent="NonExistent")

    def test_assert_and_query(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("TestMt")
        kb.assert_fact(("isa", "Dog", "Animal"), "TestMt")
        results = kb.query(("isa", "?x", "Animal"))
        assert len(results) == 1

    def test_freeze_blocks_mutations(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("TestMt")
        kb.freeze()
        with pytest.raises(RuntimeError, match="frozen"):
            kb.assert_fact(("isa", "Dog", "Animal"), "TestMt")
        with pytest.raises(RuntimeError, match="frozen"):
            kb.create_mt("AnotherMt")

    def test_query_after_freeze(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("TestMt")
        kb.assert_fact(("isa", "Dog", "Animal"), "TestMt")
        kb.freeze()
        results = kb.query(("isa", "?x", "Animal"))
        assert len(results) == 1

    def test_fact_count(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("TestMt")
        kb.assert_fact(("isa", "Dog", "Animal"), "TestMt")
        kb.assert_fact(("isa", "Cat", "Animal"), "TestMt")
        assert kb.fact_count == 2
