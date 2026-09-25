"""Tests for ActionTypeRegistry's disambiguation API (AEGIS-2903)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.guard import Guard
from aegis.guard.registry import ActionTypeRegistry, ConfusablePair, SubsumptionGraph
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader


def _registry_from_meld(text: str) -> ActionTypeRegistry:
    kb = KnowledgeBase()
    loader = MeldLoader(kb)
    loader.load_string(text, file="test.meld")
    loader.validate_disambiguation_graph()
    kb.freeze()
    return ActionTypeRegistry.from_kb(kb)


class TestSubsumptionGraph:
    def test_empty_graph_returns_false(self) -> None:
        g = SubsumptionGraph()
        assert g.is_narrower_than("A", "B") is False

    def test_self_is_not_narrower(self) -> None:
        g = SubsumptionGraph(edges={"A": ("B",)})
        assert g.is_narrower_than("A", "A") is False

    def test_direct_edge(self) -> None:
        g = SubsumptionGraph(edges={"A": ("B",)})
        assert g.is_narrower_than("A", "B") is True
        assert g.is_narrower_than("B", "A") is False

    def test_transitive_two_hops(self) -> None:
        g = SubsumptionGraph(edges={"A": ("B",), "B": ("C",)})
        assert g.is_narrower_than("A", "C") is True

    def test_transitive_three_hops(self) -> None:
        g = SubsumptionGraph(edges={"A": ("B",), "B": ("C",), "C": ("D",)})
        assert g.is_narrower_than("A", "D") is True

    def test_diamond_path(self) -> None:
        g = SubsumptionGraph(
            edges={
                "A": ("B", "C"),
                "B": ("D",),
                "C": ("D",),
            }
        )
        assert g.is_narrower_than("A", "D") is True

    def test_minimal_elements_singleton(self) -> None:
        g = SubsumptionGraph(edges={"A": ("B",)})
        assert g.minimal_elements(frozenset({"A"})) == frozenset({"A"})

    def test_minimal_elements_picks_narrowest(self) -> None:
        g = SubsumptionGraph(edges={"A": ("B",)})
        # B is broader than A, so A is the minimum.
        assert g.minimal_elements(frozenset({"A", "B"})) == frozenset({"A"})

    def test_minimal_elements_keeps_incomparable(self) -> None:
        g = SubsumptionGraph(
            edges={
                "A1": ("Top",),
                "A2": ("Top",),
            }
        )
        # A1 and A2 are incomparable; both are minimal.
        result = g.minimal_elements(frozenset({"A1", "A2", "Top"}))
        assert result == frozenset({"A1", "A2"})

    def test_minimal_elements_chain(self) -> None:
        g = SubsumptionGraph(edges={"A": ("B",), "B": ("C",)})
        # Min of {A, B, C} is {A}.
        assert g.minimal_elements(frozenset({"A", "B", "C"})) == frozenset({"A"})


class TestRegistryDisambiguationAPI:
    def test_get_description_present(self) -> None:
        registry = _registry_from_meld(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            (actionDescription readDiagnosis "Reads the diagnostic conclusion section.")
            """
        )
        assert registry.get_description("readDiagnosis") == (
            "Reads the diagnostic conclusion section."
        )

    def test_get_description_absent_returns_none(self) -> None:
        registry = _registry_from_meld(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            """
        )
        assert registry.get_description("readDiagnosis") is None

    def test_get_description_unknown_action_returns_none(self) -> None:
        registry = _registry_from_meld(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            """
        )
        assert registry.get_description("ghostAction") is None

    def test_get_synonyms_collects_all(self) -> None:
        registry = _registry_from_meld(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            (actionSynonym readDiagnosis "view diagnosis")
            (actionSynonym readDiagnosis "view diagnostic findings")
            """
        )
        synonyms = registry.get_synonyms("readDiagnosis")
        assert "view diagnosis" in synonyms
        assert "view diagnostic findings" in synonyms

    def test_get_synonyms_empty_for_action_without_them(self) -> None:
        registry = _registry_from_meld(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            """
        )
        assert registry.get_synonyms("readDiagnosis") == []

    def test_get_confusables_returns_pairs(self) -> None:
        registry = _registry_from_meld(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            (isa readPatientRecord ActionType)
            (notToBeConfusedWith readDiagnosis readPatientRecord)
            """
        )
        pairs = registry.get_confusables("readDiagnosis")
        assert pairs == [
            ConfusablePair(action_type="readDiagnosis", other="readPatientRecord")
        ]

    def test_is_narrower_than_direct(self) -> None:
        registry = _registry_from_meld(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            (isa readPatientRecord ActionType)
            (narrowerThan readDiagnosis readPatientRecord)
            (broaderThan readPatientRecord readDiagnosis)
            """
        )
        assert registry.is_narrower_than("readDiagnosis", "readPatientRecord") is True
        assert registry.is_narrower_than("readPatientRecord", "readDiagnosis") is False

    def test_is_narrower_than_transitive(self) -> None:
        registry = _registry_from_meld(
            """
            (case TestVocabMt)
            (isa A ActionType)
            (isa B ActionType)
            (isa C ActionType)
            (narrowerThan A B)
            (broaderThan B A)
            (narrowerThan B C)
            (broaderThan C B)
            """
        )
        assert registry.is_narrower_than("A", "C") is True

    def test_subsumption_graph_is_cached(self) -> None:
        registry = _registry_from_meld(
            """
            (case TestVocabMt)
            (isa A ActionType)
            (isa B ActionType)
            (narrowerThan A B)
            (broaderThan B A)
            """
        )
        g1 = registry.subsumption_graph()
        g2 = registry.subsumption_graph()
        assert g1 is g2  # identity, not just equality

    def test_subsumption_graph_only_includes_narrower_edges(self) -> None:
        registry = _registry_from_meld(
            """
            (case TestVocabMt)
            (isa A ActionType)
            (isa B ActionType)
            (isa C ActionType)
            (narrowerThan A B)
            (broaderThan B A)
            """
        )
        graph = registry.subsumption_graph()
        # Only A has a narrower edge declared.
        assert "A" in graph.edges
        assert "B" not in graph.edges
        assert "C" not in graph.edges


class TestRegistryEndToEnd:
    """AEGIS-2903 + AEGIS-2902 integration: a Guard built via
    from_meld_files exposes the full disambiguation API on its registry."""

    def test_guard_registry_has_disambiguation_data(self, tmp_path: Path) -> None:
        meld = tmp_path / "vocab.meld"
        meld.write_text(
            """
            (aegis-schema-version 1)
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            (isa readPatientRecord ActionType)
            (actionDescription readDiagnosis "Reads only the diagnostic section.")
            (actionSynonym readDiagnosis "view diagnosis")
            (notToBeConfusedWith readDiagnosis readPatientRecord)
            (narrowerThan readDiagnosis readPatientRecord)
            (broaderThan readPatientRecord readDiagnosis)
            """,
            encoding="utf-8",
        )
        guard = Guard.from_meld_files([meld])
        registry = guard._registry  # internal access for test
        assert registry.get_description("readDiagnosis") == (
            "Reads only the diagnostic section."
        )
        assert "view diagnosis" in registry.get_synonyms("readDiagnosis")
        assert registry.get_confusables("readDiagnosis") == [
            ConfusablePair(action_type="readDiagnosis", other="readPatientRecord")
        ]
        assert registry.is_narrower_than("readDiagnosis", "readPatientRecord") is True
