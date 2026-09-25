"""Tests for AEGIS-1703: Provenance-Carrying Tool Results."""

from __future__ import annotations

from aegis.ifc.provenance import ProvenancedResult, ProvenanceRecord


class TestProvenanceRecord:
    def test_frozen_dataclass(self) -> None:
        record = ProvenanceRecord(
            source_path="intel/briefing.txt",
            classification="secret",
            canary_tokens=("CANARY-1234",),
            allowed_recipients=("internalAgent",),
            allowed_purposes=("internalAnalysis",),
        )
        assert record.source_path == "intel/briefing.txt"
        assert record.classification == "secret"
        assert record.canary_tokens == ("CANARY-1234",)
        assert record.allowed_recipients == ("internalAgent",)
        assert record.allowed_purposes == ("internalAnalysis",)

    def test_defaults(self) -> None:
        record = ProvenanceRecord(source_path="test.txt", classification="public")
        assert record.canary_tokens == ()
        assert record.allowed_recipients == ()
        assert record.allowed_purposes == ()


class TestProvenancedResult:
    def test_full_content_result(self) -> None:
        record = ProvenanceRecord(source_path="a.txt", classification="public")
        result = ProvenancedResult(
            content="Hello",
            provenance=(record,),
        )
        assert result.content == "Hello"
        assert result.redacted is False
        assert result.response_mode == "full-content"
        assert result.derived_from == ()

    def test_deny_result(self) -> None:
        record = ProvenanceRecord(source_path="b.txt", classification="secret")
        result = ProvenancedResult(
            content="",
            provenance=(record,),
            redacted=True,
            response_mode="deny",
        )
        assert result.content == ""
        assert result.redacted is True
        assert result.response_mode == "deny"

    def test_metadata_only_result(self) -> None:
        result = ProvenancedResult(
            content="",
            provenance=(
                ProvenanceRecord(source_path="c.txt", classification="topSecret"),
            ),
            redacted=True,
            response_mode="metadata-only",
        )
        assert result.response_mode == "metadata-only"

    def test_derived_from(self) -> None:
        result = ProvenancedResult(
            content="summary",
            provenance=(),
            derived_from=("a.txt", "b.txt"),
        )
        assert result.derived_from == ("a.txt", "b.txt")
