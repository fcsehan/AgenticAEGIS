"""Tests for DIP coverage analysis and reference testing."""

from pathlib import Path

from aegis.dip.coverage import (
    ReferenceTestCase,
    analyze_coverage,
    load_reference_tests,
    run_reference_tests,
)
from aegis.dip.models import (
    Article,
    ChunkType,
    CompilationResult,
    NormativeChunk,
    NormativeDocument,
    NormativeStatement,
    Paragraph,
)

FIXTURES = Path(__file__).parent


class TestAnalyzeCoverage:
    def test_full_coverage(self) -> None:
        doc = NormativeDocument(
            title="Test",
            source="test",
            articles=(
                Article(number="5", title="Principles", chapter="II", chapter_title="Core",
                        paragraphs=(Paragraph(number="1", text="Must process lawfully."),)),
                Article(number="6", title="Lawfulness", chapter="II", chapter_title="Core",
                        paragraphs=(Paragraph(number="1", text="Only if consent."),)),
            ),
        )
        chunks = [
            NormativeChunk(article_ref="Art. 5(1)", text="Must process.", chunk_type=ChunkType.OBLIGATION),
            NormativeChunk(article_ref="Art. 6(1)", text="Only if consent.", chunk_type=ChunkType.PERMISSION),
        ]
        stmts = [
            NormativeStatement(source_article="Art. 5(1)", modality="OBLIGATORY", subject="controller", action="process"),
            NormativeStatement(source_article="Art. 6(1)", modality="PERMITTED", subject="controller", action="process with consent"),
        ]
        results = [
            CompilationResult(source_article="Art. 5(1)", success=True, meld_expression="(oughtToDo-WRT C a (p))"),
            CompilationResult(source_article="Art. 6(1)", success=True, meld_expression="(permittedToDo-WRT C a (p))"),
        ]
        report = analyze_coverage(doc, chunks, stmts, results)
        assert report.total_articles == 2
        assert report.articles_with_rules == 2
        assert report.coverage_ratio == 1.0

    def test_partial_coverage(self) -> None:
        doc = NormativeDocument(
            title="Test",
            source="test",
            articles=(
                Article(number="5", title="Principles", chapter="II", chapter_title="Core",
                        paragraphs=(Paragraph(number="1", text="Must."),)),
                Article(number="99", title="Entry into force", chapter="XI", chapter_title="Final",
                        paragraphs=(Paragraph(number="1", text="Enters into force."),)),
            ),
        )
        chunks = [
            NormativeChunk(article_ref="Art. 5(1)", text="Must.", chunk_type=ChunkType.OBLIGATION),
        ]
        stmts = [
            NormativeStatement(source_article="Art. 5(1)", modality="OBLIGATORY", subject="c", action="a"),
        ]
        results = [
            CompilationResult(source_article="Art. 5(1)", success=True, meld_expression="(oughtToDo-WRT C a (p))"),
        ]
        report = analyze_coverage(doc, chunks, stmts, results)
        assert report.total_articles == 2
        assert report.articles_with_rules == 1
        assert report.articles_without_rules == 1
        assert report.coverage_ratio == 0.5
        # Article 99 should explain why it was skipped
        art99 = [a for a in report.articles if a.number == "99"][0]
        assert "no normative chunks" in art99.skipped_reason

    def test_empty_document(self) -> None:
        doc = NormativeDocument(title="Empty", source="test")
        report = analyze_coverage(doc, [], [], [])
        assert report.total_articles == 0
        assert report.coverage_ratio == 0.0

    def test_to_dict(self) -> None:
        doc = NormativeDocument(
            title="Test", source="test",
            articles=(Article(number="1", title="T", chapter="I", chapter_title="C",
                              paragraphs=(Paragraph(number="1", text="X"),)),),
        )
        report = analyze_coverage(doc, [], [], [])
        d = report.to_dict()
        assert "total_articles" in d
        assert "articles" in d
        assert len(d["articles"]) == 1


class TestLoadReferenceTests:
    def test_load_gdpr(self) -> None:
        tests = load_reference_tests(FIXTURES / "reference_tests" / "gdpr.json")
        assert len(tests) >= 10
        assert all(isinstance(t, ReferenceTestCase) for t in tests)
        assert all(t.action_type for t in tests)
        assert all(t.expected_verdict in ("PERMITTED", "FORBIDDEN", "UNDECIDABLE") for t in tests)


class TestRunReferenceTests:
    def test_against_legal_domain(self) -> None:
        """Run GDPR reference tests against the manually-crafted legal domain."""
        from aegis.guard.guard import Guard
        legal_dir = Path("aegis/domains/legal")
        if not legal_dir.exists():
            return  # skip if not available

        meld_files = sorted(legal_dir.glob("*.meld"))
        guard = Guard.from_meld_files(meld_files, code_prevalence=["DataProtection"])
        tests = load_reference_tests(FIXTURES / "reference_tests" / "gdpr.json")
        report = run_reference_tests(guard, tests)

        assert report.total == len(tests)
        # At least some tests should pass against the manual domain
        assert report.passed > 0
        # Report should be serializable
        d = report.to_dict()
        assert "results" in d
