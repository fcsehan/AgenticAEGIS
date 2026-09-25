"""Tests for conflict detection."""

from __future__ import annotations

from aegis.deontic.conflicts import ConflictType, detect_conflicts
from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame


def _norm(
    modality: DeonticModality,
    code: str = "A",
    specificity: int = 0,
) -> NormFrame:
    return NormFrame(
        code=code,
        agent_pattern="*",
        modality=modality,
        proposition=("action",),
        specificity=specificity,
    )


class TestDetectConflicts:
    def test_no_conflicts(self) -> None:
        norms = [
            _norm(DeonticModality.PERMITTED),
            _norm(DeonticModality.PERMITTED),
        ]
        assert detect_conflicts(norms) == []

    def test_basic_conflict(self) -> None:
        norms = [
            _norm(DeonticModality.PERMITTED),
            _norm(DeonticModality.FORBIDDEN),
        ]
        conflicts = detect_conflicts(norms)
        assert len(conflicts) == 1

    def test_preemption_classification(self) -> None:
        norms = [
            _norm(DeonticModality.PERMITTED, specificity=2),
            _norm(DeonticModality.FORBIDDEN, specificity=1),
        ]
        conflicts = detect_conflicts(norms)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.PREEMPTION

    def test_hierarchical_classification(self) -> None:
        norms = [
            _norm(DeonticModality.PERMITTED, code="A"),
            _norm(DeonticModality.FORBIDDEN, code="B"),
        ]
        conflicts = detect_conflicts(norms)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.HIERARCHICAL

    def test_permissive_inheritance(self) -> None:
        norms = [
            _norm(DeonticModality.PERMITTED, code="A", specificity=0),
            _norm(DeonticModality.FORBIDDEN, code="A", specificity=0),
        ]
        conflicts = detect_conflicts(norms)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.PERMISSIVE_INHERITANCE
