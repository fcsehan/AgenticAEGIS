"""Tests for DIP fetcher — generic document loading."""

from pathlib import Path

import pytest

from aegis.dip.fetcher import (
    HtmlPageSource,
    PlainTextSource,
    _extract_article_number,
    _extract_litera,
    _parse_html,
    _parse_paragraphs,
    _text_to_articles,
    detect_source_type,
    extract_cross_refs,
    fetch_document,
)
from aegis.dip.models import NormativeDocument

FIXTURES = Path(__file__).parent / "fixtures"


# ── Source type detection ───────────────────────────────────────────


class TestDetectSourceType:
    def test_url_html(self) -> None:
        assert detect_source_type("https://example.com/policy.html") == "html"

    def test_url_html_index(self) -> None:
        assert detect_source_type("https://example.com/policies/topics/") == "html-index"

    def test_url_topics(self) -> None:
        assert detect_source_type("https://example.com/topics") == "html-index"

    def test_url_pdf(self) -> None:
        assert detect_source_type("https://example.com/doc.pdf") == "pdf"

    def test_local_markdown(self) -> None:
        assert detect_source_type("/tmp/policy.md") == "text"

    def test_local_html(self) -> None:
        assert detect_source_type("/tmp/page.html") == "html"

    def test_local_txt(self) -> None:
        assert detect_source_type("rules.txt") == "text"

    def test_local_pdf(self) -> None:
        assert detect_source_type("./regulation.pdf") == "pdf"

    def test_unknown(self) -> None:
        assert detect_source_type("/tmp/data.bin") == "unknown"


# ── Cross-reference extraction ──────────────────────────────────────


class TestExtractCrossRefs:
    def test_mixed_article_refs(self) -> None:
        text = "under Article 6 Paragraph 1 and Art. 9 Paragraph 2 point a"
        refs = extract_cross_refs(text)
        assert any("6" in r for r in refs)
        assert any("9" in r for r in refs)
        assert any("a" in r for r in refs)

    def test_english_section_refs(self) -> None:
        text = "See Section 5.2 and Clause 8.1 for details"
        refs = extract_cross_refs(text)
        assert any("5.2" in r for r in refs)
        assert any("8.1" in r for r in refs)

    def test_paragraph_ref(self) -> None:
        text = "Notwithstanding § 42a, the following applies"
        refs = extract_cross_refs(text)
        assert any("42a" in r for r in refs)

    def test_no_duplicates(self) -> None:
        text = "Art. 17 and Art. 17 again"
        refs = extract_cross_refs(text)
        art17_refs = [r for r in refs if "17" in r]
        assert len(art17_refs) == 1


# ── Paragraph parsing ───────────────────────────────────────────────


class TestParseParagraphs:
    def test_numbered_paragraphs(self) -> None:
        text = "(1) First paragraph.\n(2) Second paragraph."
        paras = _parse_paragraphs(text)
        assert len(paras) == 2
        assert paras[0].number == "1"
        assert paras[1].number == "2"

    def test_unnumbered(self) -> None:
        text = "This is a simple text without numbered paragraphs."
        paras = _parse_paragraphs(text)
        assert len(paras) == 1
        assert paras[0].number == ""

    def test_litera_extraction(self) -> None:
        text = "(1) Main text:\na) first item\nb) second item\nc) third"
        paras = _parse_paragraphs(text)
        assert paras[0].litera == ["a", "b", "c"]

    def test_empty_text(self) -> None:
        assert _parse_paragraphs("") == ()
        assert _parse_paragraphs("   ") == ()


class TestExtractLitera:
    def test_basic(self) -> None:
        assert _extract_litera("a) first\nb) second") == ["a", "b"]

    def test_no_litera(self) -> None:
        assert _extract_litera("no sub-items here") == []


# ── Article number extraction ───────────────────────────────────────


class TestExtractArticleNumber:
    def test_from_abbreviated_title(self) -> None:
        assert _extract_article_number("Art. 17 GDPR – Right to erasure", "") == "17"

    def test_from_english_title(self) -> None:
        assert _extract_article_number("Article 5 - Principles", "") == "5"

    def test_from_section_title(self) -> None:
        assert _extract_article_number("Section 8.1 - Endpoint devices", "") == "8.1"

    def test_from_url(self) -> None:
        assert _extract_article_number("", "https://example.com/art-17-gdpr/") == "17"

    def test_from_paragraph_sign(self) -> None:
        assert _extract_article_number("§ 42a Policy", "") == "42a"

    def test_unknown(self) -> None:
        assert _extract_article_number("Some heading", "https://example.com/page") == "?"


# ── Text to articles ────────────────────────────────────────────────


class TestTextToArticles:
    def test_article_pattern(self) -> None:
        text = (
            "Art. 5 – Principles\n"
            "Personal data must be processed lawfully.\n\n"
            "Art. 6 – Lawfulness\n"
            "(1) Processing is lawful only if...\n"
            "(2) Member states may retain more specific provisions.\n"
        )
        articles = _text_to_articles(text)
        assert len(articles) == 2
        assert articles[0].number == "5"
        assert articles[1].number == "6"
        assert len(articles[1].paragraphs) == 2

    def test_section_pattern(self) -> None:
        text = (
            "Section 5.1 - Policies\n"
            "Policies shall be defined.\n\n"
            "Section 5.2 - Roles\n"
            "Roles shall be allocated.\n"
        )
        articles = _text_to_articles(text)
        assert len(articles) == 2
        assert articles[0].number == "5.1"

    def test_no_structure(self) -> None:
        text = "This is unstructured normative text."
        articles = _text_to_articles(text)
        assert len(articles) == 1
        assert articles[0].number == "1"


# ── HTML parsing ────────────────────────────────────────────────────


class TestParseHtml:
    def test_extracts_text(self) -> None:
        html = "<html><body><p>Hello world</p></body></html>"
        parsed = _parse_html(html)
        assert "Hello world" in parsed.text

    def test_extracts_headings(self) -> None:
        html = "<h1>Title</h1><h2>Chapter</h2><p>Text</p>"
        parsed = _parse_html(html)
        assert len(parsed.headings) == 2
        assert parsed.headings[0] == (1, "Title")
        assert parsed.headings[1] == (2, "Chapter")

    def test_extracts_links(self) -> None:
        html = '<a href="/art-6/">Article 6</a>'
        parsed = _parse_html(html)
        assert len(parsed.links) == 1
        assert parsed.links[0] == ("/art-6/", "Article 6")

    def test_skips_script(self) -> None:
        html = "<p>Visible</p><script>var x = 1;</script><p>Also visible</p>"
        parsed = _parse_html(html)
        assert "var x" not in parsed.text
        assert "Visible" in parsed.text


# ── PlainTextSource ─────────────────────────────────────────────────


class TestPlainTextSource:
    def test_markdown_file(self) -> None:
        doc = PlainTextSource(
            str(FIXTURES / "sample_policy_en.md"), language="en"
        ).fetch()
        assert doc.title  # auto-detected
        assert len(doc.articles) > 0
        assert doc.language == "en"

    def test_txt_file(self) -> None:
        doc = PlainTextSource(
            str(FIXTURES / "sample_standard_en.txt"), language="en"
        ).fetch()
        assert doc.title
        assert len(doc.articles) > 0

    def test_articles_have_structure(self) -> None:
        doc = PlainTextSource(str(FIXTURES / "sample_policy_en.md")).fetch()
        # Should find articles with chapters
        numbered = [a for a in doc.articles if a.number != ""]
        assert len(numbered) > 0


# ── HtmlPageSource ──────────────────────────────────────────────────


class TestHtmlPageSource:
    def test_local_html_file(self) -> None:
        doc = HtmlPageSource(
            str(FIXTURES / "sample_article_en.html"), language="en"
        ).fetch()
        assert "erasure" in doc.title or "17" in doc.title
        assert doc.language == "en"

    def test_html_string(self) -> None:
        html = """
        <html><body>
        <h1>Test Policy</h1>
        <h2>Chapter 1</h2>
        <p>Article 1: All employees must report incidents.</p>
        <p>Article 2: Data must not be shared externally.</p>
        </body></html>
        """
        doc = HtmlPageSource(html, is_html=True, title="Test").fetch()
        assert doc.title == "Test"
        assert len(doc.articles) > 0


# ── fetch_document (public API) ─────────────────────────────────────


class TestFetchDocument:
    def test_auto_detect_markdown(self) -> None:
        doc = fetch_document(str(FIXTURES / "sample_policy_en.md"))
        assert isinstance(doc, NormativeDocument)
        assert len(doc.articles) > 0

    def test_auto_detect_html(self) -> None:
        doc = fetch_document(str(FIXTURES / "sample_article_en.html"))
        assert isinstance(doc, NormativeDocument)

    def test_auto_detect_txt(self) -> None:
        doc = fetch_document(str(FIXTURES / "sample_standard_en.txt"))
        assert isinstance(doc, NormativeDocument)
        assert len(doc.articles) > 0

    def test_explicit_source_type(self) -> None:
        doc = fetch_document(
            str(FIXTURES / "sample_policy_en.md"),
            source_type="text",
            title="Override Title",
        )
        assert doc.title == "Override Title"

    def test_pdf_not_supported(self) -> None:
        with pytest.raises(ValueError, match="PDF"):
            fetch_document("/tmp/test.pdf", source_type="pdf")

    def test_unknown_source_type(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            fetch_document("/tmp/test.bin", source_type="exotic")

    def test_markdown_has_chapters(self) -> None:
        """Markdown with ## headings should produce articles with chapters."""
        doc = fetch_document(str(FIXTURES / "sample_policy_en.md"))
        chapters = {a.chapter_title for a in doc.articles if a.chapter_title}
        assert len(chapters) > 0

    def test_standard_has_sections(self) -> None:
        """Plain text with Section X.Y should produce numbered articles."""
        doc = fetch_document(str(FIXTURES / "sample_standard_en.txt"))
        numbers = [a.number for a in doc.articles]
        assert any("." in n for n in numbers) or len(numbers) > 1
