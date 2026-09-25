"""Tests for VocabularyLoader."""

from __future__ import annotations

from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.vocabulary_loader import VocabularyLoader


class TestVocabularyLoader:
    def test_extract_action_types(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("VocabMt")
        kb.assert_fact(("isa", "shareIntelligence", "MissionActionType"), "VocabMt")
        kb.assert_fact(("isa", "directOps", "MissionActionType"), "VocabMt")
        kb.freeze()

        loader = VocabularyLoader(kb)
        schemas = loader.extract()
        assert "shareIntelligence" in schemas
        assert "directOps" in schemas

    def test_extract_parameters(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("VocabMt")
        kb.assert_fact(("isa", "share", "MissionActionType"), "VocabMt")
        kb.assert_fact(("actionParameter", "share", "dataClass", "ClassType"), "VocabMt")
        kb.freeze()

        schemas = VocabularyLoader(kb).extract()
        assert len(schemas["share"].parameters) == 1
        assert schemas["share"].parameters[0].name == "dataClass"

    def test_extract_required_context(self) -> None:
        kb = KnowledgeBase()
        kb.create_mt("VocabMt")
        kb.assert_fact(("isa", "share", "MissionActionType"), "VocabMt")
        kb.assert_fact(("requiredContext", "share", "clearance", "Level"), "VocabMt")
        kb.freeze()

        schemas = VocabularyLoader(kb).extract()
        assert len(schemas["share"].required_context) == 1
        assert schemas["share"].required_context[0].name == "clearance"
