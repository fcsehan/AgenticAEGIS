"""Tests for NormFrame."""

from __future__ import annotations

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame


def _make_norm(
    modality: DeonticModality = DeonticModality.PERMITTED,
    agent: str = "*",
    code: str = "TestCode",
    specificity: int = 0,
    prop: tuple[object, ...] = ("action",),
) -> NormFrame:
    return NormFrame(
        code=code,
        agent_pattern=agent,
        modality=modality,
        proposition=prop,
        specificity=specificity,
    )


class TestNormFrame:
    def test_frozen(self) -> None:
        norm = _make_norm()
        assert hash(norm)  # hashable

    def test_matches_agent_wildcard(self) -> None:
        norm = _make_norm(agent="*")
        assert norm.matches_agent("anyone")
        assert norm.matches_agent("agent-007")

    def test_matches_agent_exact(self) -> None:
        norm = _make_norm(agent="agent-007")
        assert norm.matches_agent("agent-007")
        assert not norm.matches_agent("agent-008")

    def test_is_more_specific(self) -> None:
        general = _make_norm(specificity=1)
        specific = _make_norm(specificity=3)
        assert specific.is_more_specific_than(general)
        assert not general.is_more_specific_than(specific)

    def test_conflicts_permitted_vs_forbidden(self) -> None:
        permitted = _make_norm(modality=DeonticModality.PERMITTED)
        forbidden = _make_norm(modality=DeonticModality.FORBIDDEN)
        assert permitted.conflicts_with(forbidden)
        assert forbidden.conflicts_with(permitted)

    def test_conflicts_obligatory_vs_forbidden(self) -> None:
        obligatory = _make_norm(modality=DeonticModality.OBLIGATORY)
        forbidden = _make_norm(modality=DeonticModality.FORBIDDEN)
        assert obligatory.conflicts_with(forbidden)

    def test_no_conflict_same_modality(self) -> None:
        a = _make_norm(modality=DeonticModality.PERMITTED)
        b = _make_norm(modality=DeonticModality.PERMITTED)
        assert not a.conflicts_with(b)

    def test_no_conflict_obligatory_vs_permitted(self) -> None:
        obligatory = _make_norm(modality=DeonticModality.OBLIGATORY)
        permitted = _make_norm(modality=DeonticModality.PERMITTED)
        assert not obligatory.conflicts_with(permitted)

    def test_hashable_in_set(self) -> None:
        a = _make_norm(agent="a")
        b = _make_norm(agent="b")
        s = {a, b, a}
        assert len(s) == 2
