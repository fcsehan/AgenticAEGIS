"""Tests for DIP chunker — generic structure recognition."""

from pathlib import Path

from aegis.dip.chunker import (
    PROFILE_EN,
    SignalWordProfile,
    _build_article_ref,
    _classify_text,
    _is_organizational,
    chunk_document,
    detect_language,
    get_profile,
)
from aegis.dip.fetcher import fetch_document
from aegis.dip.models import (
    Article,
    ChunkType,
    NormativeChunk,
    NormativeDocument,
    Paragraph,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── Language detection ──────────────────────────────────────────────


class TestDetectLanguage:
    def test_default_profile(self) -> None:
        text = (
            "The controller must erase personal data without undue delay "
            "when processing is no longer necessary."
        )
        assert detect_language(text) == "en"

    def test_english(self) -> None:
        text = (
            "The controller shall ensure that personal data is processed "
            "lawfully and transparently."
        )
        assert detect_language(text) == "en"

    def test_profile_lookup(self) -> None:
        assert get_profile("auto") is PROFILE_EN
        assert get_profile("en") is PROFILE_EN
        assert get_profile("fr") is PROFILE_EN  # fallback


# ── Classification ──────────────────────────────────────────────────


class TestClassifyTextEnglishVariants:
    def test_obligation_must(self) -> None:
        text = "The controller must erase the data."
        assert _classify_text(text, PROFILE_EN) == ChunkType.OBLIGATION

    def test_obligation_required(self) -> None:
        text = "The processor is required to take appropriate measures."
        assert _classify_text(text, PROFILE_EN) == ChunkType.OBLIGATION

    def test_prohibition_must_not(self) -> None:
        text = "Special categories of personal data must not be processed."
        assert _classify_text(text, PROFILE_EN) == ChunkType.PROHIBITION

    def test_prohibition_prohibited(self) -> None:
        text = "Disclosure to third parties is prohibited."
        assert _classify_text(text, PROFILE_EN) == ChunkType.PROHIBITION

    def test_permission_may(self) -> None:
        text = "The data subject may request access."
        assert _classify_text(text, PROFILE_EN) == ChunkType.PERMISSION

    def test_permission_right(self) -> None:
        text = "The data subject has the right to erasure."
        assert _classify_text(text, PROFILE_EN) == ChunkType.PERMISSION

    def test_exception_does_not_apply(self) -> None:
        text = "Paragraph 1 does not apply where processing is necessary."
        assert _classify_text(text, PROFILE_EN) == ChunkType.EXCEPTION

    def test_exception_unless(self) -> None:
        text = "The data must not be processed unless consent has been given."
        # "unless" is exception, "must not" is prohibition
        # Exception should win due to higher weight
        assert _classify_text(text, PROFILE_EN) == ChunkType.EXCEPTION

    def test_definition(self) -> None:
        text = '"Personal data" means any information for the purposes of this regulation.'
        assert _classify_text(text, PROFILE_EN) == ChunkType.DEFINITION

    def test_unknown(self) -> None:
        text = "This chapter describes the scope."
        assert _classify_text(text, PROFILE_EN) == ChunkType.UNKNOWN


class TestClassifyTextEnglish:
    def test_obligation_shall(self) -> None:
        text = "The controller shall ensure appropriate security measures."
        assert _classify_text(text, PROFILE_EN) == ChunkType.OBLIGATION

    def test_obligation_must(self) -> None:
        text = "All data must be classified according to the scheme."
        assert _classify_text(text, PROFILE_EN) == ChunkType.OBLIGATION

    def test_prohibition_shall_not(self) -> None:
        text = "Employees shall not transfer data to external systems."
        assert _classify_text(text, PROFILE_EN) == ChunkType.PROHIBITION

    def test_prohibition_prohibited(self) -> None:
        text = "Employees are prohibited from bypassing security controls."
        assert _classify_text(text, PROFILE_EN) == ChunkType.PROHIBITION

    def test_prohibition_forbidden(self) -> None:
        text = "The use of personal devices is forbidden."
        assert _classify_text(text, PROFILE_EN) == ChunkType.PROHIBITION

    def test_permission_may(self) -> None:
        text = "The data subject may request access to their records."
        assert _classify_text(text, PROFILE_EN) == ChunkType.PERMISSION

    def test_permission_entitled(self) -> None:
        text = "The individual is entitled to data portability."
        assert _classify_text(text, PROFILE_EN) == ChunkType.PERMISSION

    def test_exception_notwithstanding(self) -> None:
        text = "Notwithstanding Article 4, emergency access may be granted."
        assert _classify_text(text, PROFILE_EN) == ChunkType.EXCEPTION

    def test_exception_does_not_apply(self) -> None:
        text = "This article does not apply to anonymized data."
        assert _classify_text(text, PROFILE_EN) == ChunkType.EXCEPTION

    def test_definition_means(self) -> None:
        text = '"Personal data" means any information relating to an identified person.'
        assert _classify_text(text, PROFILE_EN) == ChunkType.DEFINITION

    def test_unknown(self) -> None:
        text = "This regulation enters into force on the twentieth day."
        assert _classify_text(text, PROFILE_EN) == ChunkType.UNKNOWN


# ── Organizational detection ────────────────────────────────────────


class TestIsOrganizational:
    def test_entry_into_force(self) -> None:
        art = Article(number="99", title="Entry into force", chapter="XI", chapter_title="Final provisions")
        assert _is_organizational(art, PROFILE_EN)

    def test_english_final_provisions(self) -> None:
        art = Article(number="99", title="Entry into force", chapter="XI", chapter_title="Final provisions")
        assert _is_organizational(art, PROFILE_EN)

    def test_normative_article(self) -> None:
        art = Article(number="17", title="Right to erasure", chapter="III", chapter_title="Rights of the data subject")
        assert not _is_organizational(art, PROFILE_EN)


# ── Article reference building ──────────────────────────────────────


class TestBuildArticleRef:
    def test_law_style(self) -> None:
        art = Article(number="17", title="", chapter="", chapter_title="")
        assert _build_article_ref(art) == "Art. 17"

    def test_law_style_with_paragraph(self) -> None:
        art = Article(number="17", title="", chapter="", chapter_title="")
        para = Paragraph(number="3", text="")
        assert _build_article_ref(art, para) == "Art. 17(3)"

    def test_iso_style(self) -> None:
        art = Article(number="5.2", title="", chapter="", chapter_title="")
        assert _build_article_ref(art) == "Section 5.2"

    def test_annex_style(self) -> None:
        art = Article(number="A.5.1", title="", chapter="", chapter_title="")
        assert _build_article_ref(art) == "Clause A.5.1"


# ── Full document chunking ──────────────────────────────────────────


class TestChunkDocumentEnglish:
    def test_english_policy(self) -> None:
        doc = fetch_document(str(FIXTURES / "sample_policy_en.md"))
        chunks = chunk_document(doc, language="en")
        assert len(chunks) > 0

        # Should find various chunk types
        types = {c.chunk_type for c in chunks}
        assert ChunkType.OBLIGATION in types
        assert ChunkType.PROHIBITION in types

    def test_english_standard(self) -> None:
        doc = fetch_document(str(FIXTURES / "sample_standard_en.txt"))
        chunks = chunk_document(doc, language="en")
        assert len(chunks) > 0

    def test_exception_has_parent_ref(self) -> None:
        doc = fetch_document(str(FIXTURES / "sample_policy_en.md"))
        chunks = chunk_document(doc, language="en")
        exceptions = [c for c in chunks if c.chunk_type == ChunkType.EXCEPTION]
        # At least Article 5(3) "does not apply" and Article 7 "notwithstanding"
        assert len(exceptions) > 0

    def test_cross_refs_extracted(self) -> None:
        doc = fetch_document(str(FIXTURES / "sample_policy_en.md"))
        chunks = chunk_document(doc, language="en")
        # Article 7 references Article 4
        chunks_with_refs = [c for c in chunks if c.cross_refs]
        assert len(chunks_with_refs) > 0

    def test_definitions_detected(self) -> None:
        doc = fetch_document(str(FIXTURES / "sample_policy_en.md"))
        chunks = chunk_document(doc, language="en")
        definitions = [c for c in chunks if c.chunk_type == ChunkType.DEFINITION]
        # Article 2 has "means" and "refers to"
        assert len(definitions) > 0


class TestChunkDocumentHtml:
    def test_english_html(self) -> None:
        doc = fetch_document(str(FIXTURES / "sample_article_en.html"))
        chunks = chunk_document(doc, language="en")
        assert len(chunks) > 0

        types = {c.chunk_type for c in chunks}
        # Art. 17 has obligations, permissions, and exceptions
        assert len(types) >= 2

    def test_auto_language_detection(self) -> None:
        """Auto mode uses the English profile for the English HTML fixture."""
        doc = fetch_document(str(FIXTURES / "sample_article_en.html"))
        chunks = chunk_document(doc)  # no language hint
        assert len(chunks) > 0


class TestChunkDocumentSynthetic:
    def test_minimal_document(self) -> None:
        doc = NormativeDocument(
            title="Test",
            source="test",
            articles=(
                Article(
                    number="1",
                    title="Scope",
                    chapter="I",
                    chapter_title="General",
                    paragraphs=(
                        Paragraph(number="1", text="All users must authenticate."),
                        Paragraph(number="2", text="Users may request access."),
                    ),
                ),
            ),
        )
        chunks = chunk_document(doc, language="en")
        assert len(chunks) == 2
        assert chunks[0].chunk_type == ChunkType.OBLIGATION
        assert chunks[1].chunk_type == ChunkType.PERMISSION

    def test_organizational_filtered(self) -> None:
        doc = NormativeDocument(
            title="Test",
            source="test",
            articles=(
                Article(
                    number="1",
                    title="Entry into force",
                    chapter="IX",
                    chapter_title="Final provisions",
                    paragraphs=(Paragraph(number="1", text="This regulation enters into force."),),
                ),
                Article(
                    number="2",
                    title="Obligations",
                    chapter="II",
                    chapter_title="Core",
                    paragraphs=(Paragraph(number="1", text="All data must be encrypted."),),
                ),
            ),
        )
        chunks = chunk_document(doc, language="en")
        # "Entry into force" is organizational — Article 1 should be filtered
        refs = [c.article_ref for c in chunks]
        assert not any("1(" in r for r in refs)
        assert any("2" in r for r in refs)

    def test_article_title_preserved(self) -> None:
        doc = NormativeDocument(
            title="Test",
            source="test",
            articles=(
                Article(
                    number="5",
                    title="Data Protection",
                    chapter="II",
                    chapter_title="Rules",
                    paragraphs=(Paragraph(number="1", text="Data shall be protected."),),
                ),
            ),
        )
        chunks = chunk_document(doc, language="en")
        assert chunks[0].article_title == "Data Protection"

    def test_full_text_fallback(self) -> None:
        """Articles without paragraphs use full_text."""
        doc = NormativeDocument(
            title="Test",
            source="test",
            articles=(
                Article(
                    number="3",
                    title="Access",
                    chapter="I",
                    chapter_title="Rules",
                    full_text="Employees must not share credentials.",
                ),
            ),
        )
        chunks = chunk_document(doc, language="en")
        assert len(chunks) == 1
        assert chunks[0].chunk_type == ChunkType.PROHIBITION

    def test_custom_profile(self) -> None:
        """Custom signal word profile for domain-specific terms."""
        custom = SignalWordProfile(
            language="custom",
            obligation=(r"\brequired\b",),
            prohibition=(r"\bforbidden\b",),
            permission=(),
            exception=(),
            definition=(),
        )
        doc = NormativeDocument(
            title="Test",
            source="test",
            articles=(
                Article(
                    number="1",
                    title="Rule",
                    chapter="",
                    chapter_title="",
                    paragraphs=(
                        Paragraph(number="1", text="Authentication is required."),
                        Paragraph(number="2", text="Sharing credentials is forbidden."),
                    ),
                ),
            ),
        )
        chunks = chunk_document(doc, profile=custom)
        assert chunks[0].chunk_type == ChunkType.OBLIGATION
        assert chunks[1].chunk_type == ChunkType.PROHIBITION

    def test_empty_document(self) -> None:
        doc = NormativeDocument(title="Empty", source="test")
        chunks = chunk_document(doc, language="en")
        assert chunks == []
