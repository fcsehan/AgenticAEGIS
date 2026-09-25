"""Tests for DeonticModality."""

from __future__ import annotations

import pytest

from aegis.deontic.modality import DEONTIC_PREDICATES, DeonticModality


class TestDeonticModality:
    def test_three_modalities(self) -> None:
        assert len(DeonticModality) == 3

    def test_negation_obligatory(self) -> None:
        assert DeonticModality.OBLIGATORY.negation() == DeonticModality.FORBIDDEN

    def test_negation_forbidden(self) -> None:
        assert DeonticModality.FORBIDDEN.negation() == DeonticModality.PERMITTED

    def test_negation_permitted(self) -> None:
        assert DeonticModality.PERMITTED.negation() == DeonticModality.FORBIDDEN

    def test_from_meld_ought_to_do(self) -> None:
        assert DeonticModality.from_meld_predicate("oughtToDo") == DeonticModality.OBLIGATORY

    def test_from_meld_forbidden_to_do(self) -> None:
        assert DeonticModality.from_meld_predicate("forbiddenToDo") == DeonticModality.FORBIDDEN

    def test_from_meld_permitted_to_do(self) -> None:
        assert DeonticModality.from_meld_predicate("permittedToDo") == DeonticModality.PERMITTED

    def test_from_meld_wrt_variants(self) -> None:
        assert DeonticModality.from_meld_predicate("oughtToDo-WRT") == DeonticModality.OBLIGATORY
        assert DeonticModality.from_meld_predicate("forbiddenToDo-WRT") == DeonticModality.FORBIDDEN
        assert DeonticModality.from_meld_predicate("permittedToDo-WRT") == DeonticModality.PERMITTED

    def test_from_meld_to_be_variants(self) -> None:
        assert DeonticModality.from_meld_predicate("oughtToBe") == DeonticModality.OBLIGATORY
        assert DeonticModality.from_meld_predicate("forbiddenToBe") == DeonticModality.FORBIDDEN
        assert DeonticModality.from_meld_predicate("permittedToBe") == DeonticModality.PERMITTED

    def test_from_meld_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown deontic predicate"):
            DeonticModality.from_meld_predicate("notADeonticPred")

    def test_all_nine_predicates_covered(self) -> None:
        assert len(DEONTIC_PREDICATES) == 9
        for pred in DEONTIC_PREDICATES:
            DeonticModality.from_meld_predicate(pred)  # should not raise
