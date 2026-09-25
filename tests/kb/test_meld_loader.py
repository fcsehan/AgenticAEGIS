"""Tests for MELD Loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.deontic.modality import DeonticModality
from aegis.errors import MeldSyntaxError
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader, extract_norm, parse_meld


class TestParseMeld:
    def test_simple_assertion(self) -> None:
        result = parse_meld("(isa Dog Animal)")
        assert result == [("isa", "Dog", "Animal")]

    def test_multiple_assertions(self) -> None:
        result = parse_meld("(isa Dog Animal)\n(genls Dog Animal)")
        assert len(result) == 2

    def test_nested_expression(self) -> None:
        result = parse_meld("(isa (ModalOpSetFn ought-c IntelligentAgent) Type)")
        assert len(result) == 1
        assert result[0] == ("isa", ("ModalOpSetFn", "ought-c", "IntelligentAgent"), "Type")

    def test_string_literal(self) -> None:
        result = parse_meld('(comment oughtToDo "This is a comment")')
        assert result[0] == ("comment", "oughtToDo", "This is a comment")

    def test_multiline_string(self) -> None:
        result = parse_meld('(comment foo "line1\nline2")')
        assert "\n" in result[0][2]

    def test_integer_literal(self) -> None:
        result = parse_meld("(aegis-schema-version 1)")
        assert result[0] == ("aegis-schema-version", 1)

    def test_empty_assertion_raises(self) -> None:
        with pytest.raises(MeldSyntaxError, match="Empty assertion"):
            parse_meld("()")

    def test_unclosed_paren_raises(self) -> None:
        with pytest.raises(MeldSyntaxError, match="Unclosed parenthesis"):
            parse_meld("(isa Dog")

    def test_unclosed_string_raises(self) -> None:
        with pytest.raises(MeldSyntaxError, match="Unterminated string"):
            parse_meld('(comment foo "unterminated')

    def test_escaped_quote_in_string(self) -> None:
        result = parse_meld(r'(comment foo "say \"hello\"")')
        assert '"' in result[0][2]


class TestExtractNorm:
    def test_ought_to_do(self) -> None:
        norm = extract_norm(("oughtToDo", "agent", "prop"), "TestMt", "test:1")
        assert norm is not None
        assert norm.modality == DeonticModality.OBLIGATORY
        assert norm.agent_pattern == "agent"

    def test_forbidden_to_do_wrt(self) -> None:
        norm = extract_norm(("forbiddenToDo-WRT", "Code", "agent", "prop"), "TestMt", "test:1")
        assert norm is not None
        assert norm.modality == DeonticModality.FORBIDDEN
        assert norm.code == "Code"
        assert norm.agent_pattern == "agent"

    def test_ought_to_be(self) -> None:
        norm = extract_norm(("oughtToBe", "prop"), "TestMt", "test:1")
        assert norm is not None
        assert norm.agent_pattern == "*"

    def test_non_deontic_returns_none(self) -> None:
        assert extract_norm(("isa", "Dog", "Animal"), "TestMt", "test:1") is None

    def test_wrong_arity_raises(self) -> None:
        with pytest.raises(MeldSyntaxError, match="expects 2 arguments"):
            extract_norm(("oughtToDo", "only-one-arg"), "TestMt", "test:1")


class TestMeldLoaderIntegration:
    def test_load_string(self) -> None:
        kb = KnowledgeBase()
        loader = MeldLoader(kb)
        loader.load_string("""
            (case TestMt)
            (isa Dog Animal)
            (genls Dog Animal)
        """)
        assert kb.fact_count == 2
        assert "TestMt" in kb.microtheories

    def test_case_switching(self) -> None:
        kb = KnowledgeBase()
        loader = MeldLoader(kb)
        loader.load_string("""
            (case Mt1)
            (isa Dog Animal)
            (case Mt2)
            (isa Cat Animal)
        """)
        assert len(kb.facts_in_mt("Mt1")) == 1
        assert len(kb.facts_in_mt("Mt2")) == 1

    def test_deontic_extraction(self) -> None:
        kb = KnowledgeBase()
        loader = MeldLoader(kb)
        loader.load_string("""
            (case RulesMt)
            (forbiddenToDo-WRT TestCode agent (doSomething bad))
            (permittedToDo-WRT TestCode agent (doSomething good))
        """)
        assert len(loader.norms) == 2
        assert loader.norms[0].modality == DeonticModality.FORBIDDEN
        assert loader.norms[1].modality == DeonticModality.PERMITTED

    def test_schema_version(self) -> None:
        kb = KnowledgeBase()
        loader = MeldLoader(kb)
        loader.load_string("""
            (aegis-schema-version 1)
            (case TestMt)
            (isa Dog Animal)
        """)
        assert loader.schema_version == 1

    def test_unknown_schema_version_raises(self) -> None:
        kb = KnowledgeBase()
        loader = MeldLoader(kb)
        with pytest.raises(MeldSyntaxError, match="Unknown schema version"):
            loader.load_string("(aegis-schema-version 99)")

    def test_missing_case_raises(self) -> None:
        kb = KnowledgeBase()
        loader = MeldLoader(kb)
        with pytest.raises(MeldSyntaxError, match="No microtheory declared"):
            loader.load_string("(isa Dog Animal)")

    def test_load_reference_meld(self) -> None:
        """Load the real DeonticReasoning .meld file."""
        meld_path = Path("Referenz/opencyc-flatfiles/DeonticReasoningWithMultiFuture-LogicMt.meld")
        if not meld_path.exists():
            pytest.skip("Reference .meld file not found")
        kb = KnowledgeBase()
        loader = MeldLoader(kb)
        loader.load_file(meld_path)
        assert kb.fact_count > 0

    def test_load_ia_mission_meld(self) -> None:
        """Load the real IAMission .meld file."""
        meld_path = Path("Referenz/opencyc-flatfiles/IAMissionObligationVocabMt.meld")
        if not meld_path.exists():
            pytest.skip("Reference .meld file not found")
        kb = KnowledgeBase()
        loader = MeldLoader(kb)
        loader.load_file(meld_path)
        assert kb.fact_count > 0
