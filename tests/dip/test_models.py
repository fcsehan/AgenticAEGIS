"""Tests for DIP data models."""

from aegis.dip.models import (
    Article,
    ChunkType,
    CompilationResult,
    DomainExport,
    DomainOntology,
    NormativeChunk,
    NormativeDocument,
    NormativeStatement,
    OntologyAction,
    OntologyRole,
    Paragraph,
    ReviewFlag,
)


class TestArticle:
    def test_creation(self) -> None:
        p = Paragraph(number="1", text="Test paragraph.", litera=["a", "b"])
        a = Article(number="6", title="Lawfulness", chapter="II", chapter_title="Principles", paragraphs=(p,))
        assert a.number == "6"
        assert len(a.paragraphs) == 1
        assert a.paragraphs[0].litera == ["a", "b"]

    def test_frozen(self) -> None:
        a = Article(number="1", title="t", chapter="I", chapter_title="c")
        try:
            a.number = "2"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass

    def test_iso_style_numbering(self) -> None:
        """Articles can use ISO-style numbering (A.5.1)."""
        a = Article(number="A.5.1", title="Access control", chapter="A.5", chapter_title="Organizational controls")
        assert a.number == "A.5.1"
        assert a.chapter == "A.5"


class TestNormativeDocument:
    def test_creation(self) -> None:
        doc = NormativeDocument(
            title="Test Policy",
            source="/tmp/policy.md",
            language="en",
        )
        assert doc.title == "Test Policy"
        assert doc.source == "/tmp/policy.md"
        assert doc.language == "en"

    def test_with_articles(self) -> None:
        a = Article(number="1", title="Scope", chapter="I", chapter_title="General")
        doc = NormativeDocument(title="Test", source="https://example.com", articles=(a,))
        assert len(doc.articles) == 1

    def test_metadata(self) -> None:
        doc = NormativeDocument(
            title="GDPR",
            source="https://example.com/gdpr",
            metadata={"jurisdiction": "EU", "year": "2016"},
        )
        assert doc.metadata["jurisdiction"] == "EU"


class TestNormativeChunk:
    def test_obligation(self) -> None:
        c = NormativeChunk(
            article_ref="Art. 5(1)",
            text="The controller must...",
            chunk_type=ChunkType.OBLIGATION,
        )
        assert c.chunk_type == ChunkType.OBLIGATION

    def test_exception_with_parent(self) -> None:
        c = NormativeChunk(
            article_ref="Art. 17(3)",
            text="Paragraph 1 shall not apply...",
            chunk_type=ChunkType.EXCEPTION,
            parent_ref="Art. 17(1)",
            cross_refs=("Art. 17(1)",),
        )
        assert c.parent_ref == "Art. 17(1)"


class TestNormativeStatement:
    def test_full(self) -> None:
        s = NormativeStatement(
            source_article="Art. 17(1)",
            modality="OBLIGATORY",
            subject="data controller",
            action="deletion of personal data",
            object_description="upon request of the data subject",
            conditions=("purpose no longer necessary", "consent withdrawn"),
            exceptions=("Art. 17(3)",),
            vague_terms=("without undue delay",),
            confidence=0.9,
        )
        assert s.modality == "OBLIGATORY"
        assert len(s.conditions) == 2
        assert "without undue delay" in s.vague_terms


class TestDomainOntology:
    def test_roles_and_actions(self) -> None:
        onto = DomainOntology(
            roles=(
                OntologyRole("data controller", "dataController"),
                OntologyRole("data subject", "dataSubject"),
            ),
            actions=(
                OntologyAction("deletion", "deleteData", parameters=("dataCategory",)),
            ),
            data_categories=("personalData", "medicalData"),
            role_map={"data controller": "dataController"},
            action_map={"deletion": "deleteData"},
        )
        assert len(onto.roles) == 2
        assert onto.role_map["data controller"] == "dataController"
        assert onto.actions[0].parameters == ("dataCategory",)


class TestDomainExport:
    def test_summary(self) -> None:
        export = DomainExport(
            domain_name="gdpr",
            total_rules=170,
            auto_generated=118,
            flagged_for_review=52,
            articles_processed=60,
            articles_skipped=39,
            obligations=72,
            prohibitions=28,
            permissions=70,
        )
        s = export.summary()
        assert "170 rules" in s
        assert "118 auto-generated" in s
        assert "52 flagged" in s
