"""Tests for NormStatus."""

from __future__ import annotations

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_status import NormStatus


class TestNormStatus:
    def test_is_permitted(self) -> None:
        s = NormStatus(modality=DeonticModality.PERMITTED)
        assert s.is_permitted()
        assert not s.is_forbidden()
        assert not s.is_undetermined()

    def test_is_forbidden(self) -> None:
        s = NormStatus(modality=DeonticModality.FORBIDDEN)
        assert s.is_forbidden()
        assert not s.is_permitted()

    def test_is_obligatory(self) -> None:
        s = NormStatus(modality=DeonticModality.OBLIGATORY)
        assert s.is_obligatory()

    def test_is_undetermined(self) -> None:
        s = NormStatus(modality=None)
        assert s.is_undetermined()

    def test_explain_contains_status(self) -> None:
        s = NormStatus(
            modality=DeonticModality.PERMITTED,
            reason="specificity",
        )
        text = s.explain()
        assert "PERMITTED" in text
        assert "specificity" in text

    def test_explain_undetermined(self) -> None:
        s = NormStatus(modality=None)
        text = s.explain()
        assert "UNDETERMINED" in text
