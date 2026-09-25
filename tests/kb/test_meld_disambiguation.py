"""Tests for MELD disambiguation predicates and Subsumption consistency.

AEGIS-2901 (Epic 29): the loader must accept the new Action-Substitution
disambiguation predicates and refuse inconsistent or cyclic Subsumption
graphs at domain-load time (fail-closed).

AEGIS-2902: the validator runs automatically inside ``Guard.from_meld_files``
and ``Guard.from_meld_ddic_files``. Hypothesis property test verifies that
random valid graphs always pass and that any introduced cycle is caught.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aegis.errors import MeldSyntaxError
from aegis.guard.guard import Guard
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import (
    DISAMBIGUATION_PREDICATES,
    MeldLoader,
    check_disambiguation_graph,
)


def _load(text: str) -> MeldLoader:
    kb = KnowledgeBase()
    loader = MeldLoader(kb)
    loader.load_string(text, file="test.meld")
    return loader


class TestDisambiguationPredicateRegistry:
    def test_all_five_predicates_are_registered(self) -> None:
        assert frozenset(
            {
                "actionDescription",
                "actionSynonym",
                "notToBeConfusedWith",
                "narrowerThan",
                "broaderThan",
            }
        ) == DISAMBIGUATION_PREDICATES


class TestDisambiguationLoading:
    def test_loader_accepts_actionDescription(self) -> None:
        loader = _load(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            (actionDescription readDiagnosis "Reads the diagnostic conclusion section.")
            """
        )
        loader.validate_disambiguation_graph()  # no edges, no error

    def test_loader_accepts_synonyms_and_confusables(self) -> None:
        loader = _load(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            (isa readPatientRecord ActionType)
            (actionSynonym readDiagnosis "view diagnosis")
            (actionSynonym readDiagnosis "view diagnostic findings")
            (notToBeConfusedWith readDiagnosis readPatientRecord)
            """
        )
        loader.validate_disambiguation_graph()


class TestSubsumptionBidirectional:
    def test_narrower_with_matching_broader_passes(self) -> None:
        loader = _load(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            (isa readPatientRecord ActionType)
            (narrowerThan readDiagnosis readPatientRecord)
            (broaderThan readPatientRecord readDiagnosis)
            """
        )
        loader.validate_disambiguation_graph()

    def test_narrower_without_broader_fails(self) -> None:
        loader = _load(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            (isa readPatientRecord ActionType)
            (narrowerThan readDiagnosis readPatientRecord)
            """
        )
        with pytest.raises(MeldSyntaxError, match="no matching .broaderThan"):
            loader.validate_disambiguation_graph()

    def test_broader_without_narrower_fails(self) -> None:
        loader = _load(
            """
            (case TestVocabMt)
            (isa readDiagnosis ActionType)
            (isa readPatientRecord ActionType)
            (broaderThan readPatientRecord readDiagnosis)
            """
        )
        with pytest.raises(MeldSyntaxError, match="no matching .narrowerThan"):
            loader.validate_disambiguation_graph()


class TestSubsumptionAcyclic:
    def test_simple_chain_passes(self) -> None:
        loader = _load(
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
        loader.validate_disambiguation_graph()

    def test_two_node_cycle_fails(self) -> None:
        loader = _load(
            """
            (case TestVocabMt)
            (isa A ActionType)
            (isa B ActionType)
            (narrowerThan A B)
            (broaderThan B A)
            (narrowerThan B A)
            (broaderThan A B)
            """
        )
        with pytest.raises(MeldSyntaxError, match="Cycle in narrowerThan"):
            loader.validate_disambiguation_graph()

    def test_three_node_cycle_fails(self) -> None:
        loader = _load(
            """
            (case TestVocabMt)
            (isa A ActionType)
            (isa B ActionType)
            (isa C ActionType)
            (narrowerThan A B)
            (broaderThan B A)
            (narrowerThan B C)
            (broaderThan C B)
            (narrowerThan C A)
            (broaderThan A C)
            """
        )
        with pytest.raises(MeldSyntaxError, match="Cycle in narrowerThan"):
            loader.validate_disambiguation_graph()


class TestArityValidation:
    def test_narrower_with_wrong_arity_fails(self) -> None:
        with pytest.raises(MeldSyntaxError, match="expects exactly 2"):
            _load(
                """
                (case TestVocabMt)
                (narrowerThan singleArg)
                """
            )

    def test_broader_with_wrong_arity_fails(self) -> None:
        with pytest.raises(MeldSyntaxError, match="expects exactly 2"):
            _load(
                """
                (case TestVocabMt)
                (broaderThan A B C)
                """
            )


class TestGuardIntegration:
    """AEGIS-2902: the validator must run automatically inside both
    Guard load entry points so a malformed Subsumption never reaches
    Epic 32 evaluation."""

    def test_from_meld_files_v1_path_blocks_cycle(self, tmp_path: Path) -> None:
        meld = tmp_path / "v1_cycle.meld"
        meld.write_text(
            """
            (aegis-schema-version 1)
            (case TestVocabMt)
            (isa A ActionType)
            (isa B ActionType)
            (narrowerThan A B)
            (broaderThan B A)
            (narrowerThan B A)
            (broaderThan A B)
            """,
            encoding="utf-8",
        )
        with pytest.raises(MeldSyntaxError, match="Cycle in narrowerThan"):
            Guard.from_meld_files([meld])

    def test_from_meld_ddic_files_blocks_cycle(self, tmp_path: Path) -> None:
        meld = tmp_path / "v2_cycle.meld"
        meld.write_text(
            """
            (aegis-schema-version 2)
            (case TestVocabMt)
            (isa A MissionActionType)
            (isa B MissionActionType)
            (narrowerThan A B)
            (broaderThan B A)
            (narrowerThan B A)
            (broaderThan A B)
            """,
            encoding="utf-8",
        )
        with pytest.raises(MeldSyntaxError, match="Cycle in narrowerThan"):
            Guard.from_meld_ddic_files([meld])

    def test_from_meld_files_blocks_missing_inverse(self, tmp_path: Path) -> None:
        meld = tmp_path / "v1_one_sided.meld"
        meld.write_text(
            """
            (aegis-schema-version 1)
            (case TestVocabMt)
            (isa A ActionType)
            (isa B ActionType)
            (narrowerThan A B)
            """,
            encoding="utf-8",
        )
        with pytest.raises(MeldSyntaxError, match="no matching"):
            Guard.from_meld_files([meld])


# ── Hypothesis property tests ────────────────────────────────────────


_Edges = list[tuple[str, str, str]]


def _bidir(edges: list[tuple[int, int]]) -> tuple[_Edges, _Edges]:
    """Helper: turn integer-pair edges into bidirectional narrower/broader
    triple lists with stable file/line markers."""
    narrower = [(f"A{a}", f"A{b}", "test:0") for a, b in edges]
    broader = [(f"A{b}", f"A{a}", "test:0") for a, b in edges]
    return narrower, broader


@settings(deadline=500, suppress_health_check=[HealthCheck.too_slow], max_examples=80)
@given(
    n=st.integers(min_value=2, max_value=6),
    edge_count=st.integers(min_value=0, max_value=10),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_random_dag_passes_validation(n: int, edge_count: int, seed: int) -> None:
    """Property: any DAG (bidirectional + acyclic by construction) must
    pass ``check_disambiguation_graph`` without raising. We generate a
    DAG by only allowing edges from a lower index to a higher one."""
    import random

    rng = random.Random(seed)
    pairs: set[tuple[int, int]] = set()
    for _ in range(edge_count):
        a = rng.randint(0, n - 2)
        b = rng.randint(a + 1, n - 1)
        pairs.add((a, b))

    narrower, broader = _bidir(list(pairs))
    # Should not raise.
    check_disambiguation_graph(narrower, broader)


@settings(deadline=500, suppress_health_check=[HealthCheck.too_slow], max_examples=40)
@given(
    n=st.integers(min_value=2, max_value=5),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_introduced_cycle_is_always_detected(n: int, seed: int) -> None:
    """Property: building a DAG and then adding a single back-edge from
    a higher index to a lower one must always trip the cycle check."""
    import random

    rng = random.Random(seed)
    forward: set[tuple[int, int]] = set()
    # Make a small chain so the back-edge has somewhere to land.
    for i in range(n - 1):
        forward.add((i, i + 1))
    # Optionally add some extra forward edges.
    for _ in range(rng.randint(0, 3)):
        a = rng.randint(0, n - 2)
        b = rng.randint(a + 1, n - 1)
        forward.add((a, b))
    back_a = rng.randint(1, n - 1)
    back_b = rng.randint(0, back_a - 1)
    edges = list(forward) + [(back_a, back_b)]

    narrower, broader = _bidir(edges)
    with pytest.raises(MeldSyntaxError, match="Cycle in narrowerThan"):
        check_disambiguation_graph(narrower, broader)
