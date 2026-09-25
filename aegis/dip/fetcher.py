"""Stage 1: Generic document fetcher with strategy pattern.

Loads normative documents from various sources (HTML pages, index URLs,
plain text files) and converts them to NormativeDocument objects.

Each source type has its own DocumentSource implementation. The public
function ``fetch_document()`` auto-detects the source type or accepts
an explicit ``source_type`` parameter.
"""

from __future__ import annotations

import logging
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from aegis.dip.models import Article, NormativeDocument, Paragraph

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_RATE_LIMIT_DELAY = 0.5  # seconds between HTTP requests


# ── Protocol ────────────────────────────────────────────────────────


class DocumentSource(Protocol):
    """Protocol for document source strategies."""

    def fetch(self) -> NormativeDocument: ...


# ── HTML utilities ──────────────────────────────────────────────────


class _StructureParser(HTMLParser):
    """Extracts structured text, headings, lists, and links from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self._text_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._headings: list[tuple[int, str]] = []  # (level, text)
        self._links: list[tuple[str, str]] = []  # (href, text)
        self._current_heading: str = ""
        self._in_heading: int = 0  # heading level, 0 = not in heading
        self._in_link: str = ""  # href
        self._link_text: str = ""
        self._skip = False  # skip script/style content

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag_stack.append(tag)
        if tag in ("script", "style", "noscript"):
            self._skip = True
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._in_heading = int(tag[1])
            self._current_heading = ""
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href:
                self._in_link = href
                self._link_text = ""
        if tag in ("p", "div", "li", "br", "tr", "th", "td"):
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        if tag in ("script", "style", "noscript"):
            self._skip = False
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if self._in_heading:
                self._headings.append((self._in_heading, self._current_heading.strip()))
                self._text_parts.append(f"\n## {self._current_heading.strip()}\n")
            self._in_heading = 0
        if tag == "a" and self._in_link:
            self._links.append((self._in_link, self._link_text.strip()))
            self._in_link = ""

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_heading:
            self._current_heading += data
        if self._in_link:
            self._link_text += data
        self._text_parts.append(data)

    @property
    def text(self) -> str:
        return "".join(self._text_parts)

    @property
    def headings(self) -> list[tuple[int, str]]:
        return self._headings

    @property
    def links(self) -> list[tuple[str, str]]:
        return self._links


def _parse_html(html: str) -> _StructureParser:
    """Parse HTML and return structured content."""
    parser = _StructureParser()
    parser.feed(html)
    return parser


def _http_get(url: str, *, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Fetch URL content with User-Agent header."""
    req = Request(url, headers={"User-Agent": "AEGIS-DIP/1.0"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


# ── Cross-reference extraction ──────────────────────────────────────

# Patterns for common cross-reference formats
_CROSS_REF_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Art\.?\s*(\d+)", re.IGNORECASE),  # Art. 6
    re.compile(r"Section\s+(\d+(?:\.\d+)*)", re.IGNORECASE),  # Section 5.2
    re.compile(r"Clause\s+(\d+(?:\.\d+)*)", re.IGNORECASE),  # Clause A.5.1
    re.compile(r"§\s*(\d+[a-z]?)", re.IGNORECASE),  # § 42a
    re.compile(r"Article\s+(\d+)", re.IGNORECASE),  # Article 17
    re.compile(r"Paragraph\s*(\d+)", re.IGNORECASE),  # Paragraph 1
    re.compile(r"(?:lit|point)\.?\s*([a-z])", re.IGNORECASE),  # lit. a
)


def extract_cross_refs(text: str) -> tuple[str, ...]:
    """Extract cross-references from normative text.

    Returns de-duplicated references in order of first appearance.
    """
    refs: list[str] = []
    seen: set[str] = set()
    for pattern in _CROSS_REF_PATTERNS:
        for match in pattern.finditer(text):
            ref = match.group(0).strip()
            if ref not in seen:
                refs.append(ref)
                seen.add(ref)
    return tuple(refs)


# ── Text → Article parsing ──────────────────────────────────────────

# Regex to split structured text into numbered articles/sections
_ARTICLE_SPLIT = re.compile(
    r"(?:^|\n)"
    r"(?:"
    r"(?:Art(?:icle)?\.?\s*(\d+))"  # Art. 6 / Article 6
    r"|(?:Section\s+(\d+(?:\.\d+)*))"  # Section 5.2
    r"|(?:§\s*(\d+[a-z]?))"  # § 42a
    r")"
    r"[:\s\u2013\u2014\-–—]*"  # separator chars
    r"(.*?)(?=\n|$)",  # title text
    re.IGNORECASE,
)

_PARAGRAPH_SPLIT = re.compile(
    r"(?:^|\n)\s*\((\d+)\)\s*",  # (1), (2), (3) style
)

_LITERA_SPLIT = re.compile(
    r"(?:^|\n)\s*([a-z])\)\s*",  # a), b), c) style
)


def _parse_paragraphs(text: str) -> tuple[Paragraph, ...]:
    """Parse numbered paragraphs and their litera from text."""
    parts = _PARAGRAPH_SPLIT.split(text)
    if len(parts) <= 1:
        # No numbered paragraphs — treat entire text as one paragraph
        stripped = text.strip()
        if not stripped:
            return ()
        litera = _extract_litera(stripped)
        return (Paragraph(number="", text=stripped, litera=litera),)

    paragraphs: list[Paragraph] = []
    # parts[0] is text before first paragraph number (often empty)
    i = 1
    while i < len(parts) - 1:
        num = parts[i]
        body = parts[i + 1].strip()
        litera = _extract_litera(body)
        paragraphs.append(Paragraph(number=num, text=body, litera=litera))
        i += 2
    return tuple(paragraphs)


def _extract_litera(text: str) -> list[str]:
    """Extract litera markers (a, b, c, ...) from text."""
    found = _LITERA_SPLIT.findall(text)
    return sorted(set(found))


def _text_to_articles(
    text: str,
    *,
    default_chapter: str = "",
    default_chapter_title: str = "",
    source_url: str = "",
) -> list[Article]:
    """Parse plain/structured text into Article objects."""
    matches = list(_ARTICLE_SPLIT.finditer(text))
    if not matches:
        # No recognizable article structure — return single article
        stripped = text.strip()
        if not stripped:
            return []
        paragraphs = _parse_paragraphs(stripped)
        return [
            Article(
                number="1",
                title="",
                chapter=default_chapter,
                chapter_title=default_chapter_title,
                paragraphs=paragraphs,
                full_text=stripped,
                url=source_url,
            )
        ]

    articles: list[Article] = []
    for idx, match in enumerate(matches):
        # Determine article number from whichever group matched
        number = match.group(1) or match.group(2) or match.group(3) or ""
        title = (match.group(4) or "").strip()

        # Get body text until next article
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        paragraphs = _parse_paragraphs(body)
        articles.append(
            Article(
                number=number,
                title=title,
                chapter=default_chapter,
                chapter_title=default_chapter_title,
                paragraphs=paragraphs,
                full_text=body,
                url=source_url,
            )
        )
    return articles


# ── Heading-based chapter detection ─────────────────────────────────


def _detect_chapters(
    headings: list[tuple[int, str]],
) -> dict[str, tuple[str, str]]:
    """Map heading text → (chapter_number, chapter_title).

    Uses the heading hierarchy to identify chapters:
    h1/h2 are chapters, h3+ are articles within chapters.
    """
    chapters: dict[str, tuple[str, str]] = {}
    current_chapter = ("", "")
    chapter_counter = 0
    for level, text in headings:
        if level <= 2:
            chapter_counter += 1
            # Try to extract chapter number from text
            m = re.match(r"Chapter\s+(\S+)", text, re.IGNORECASE)
            num = m.group(1) if m else str(chapter_counter)
            current_chapter = (num, text)
        else:
            chapters[text] = current_chapter
    return chapters


# ── Source implementations ──────────────────────────────────────────


class PlainTextSource:
    """Load a normative document from a local text/markdown file."""

    def __init__(self, path: str, *, title: str = "", language: str = "") -> None:
        self._path = Path(path)
        self._title = title
        self._language = language

    def fetch(self) -> NormativeDocument:
        text = self._path.read_text(encoding="utf-8")
        title = self._title or self._path.stem.replace("-", " ").replace("_", " ").title()

        # Try heading-based structure first
        lines = text.split("\n")
        sections = _split_by_headings(lines)

        # Only use heading-based parsing if we found actual headings
        has_headings = any(marker for marker, _, _ in sections)
        if has_headings:
            articles = _sections_to_articles(sections)
        else:
            articles = _text_to_articles(text, source_url=str(self._path))

        return NormativeDocument(
            title=title,
            source=str(self._path),
            articles=tuple(articles),
            language=self._language,
        )


def _split_by_headings(
    lines: list[str],
) -> list[tuple[str, str, list[str]]]:
    """Split text by markdown headings.

    Returns list of (heading_marker, heading_text, body_lines).
    Recognizes: ## Heading, === underline, --- underline.
    """
    sections: list[tuple[str, str, list[str]]] = []
    current_heading = ""
    current_marker = ""
    current_body: list[str] = []

    for i, line in enumerate(lines):
        # ATX heading (## Title)
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            if current_heading or current_body:
                sections.append((current_marker, current_heading, current_body))
            current_marker = m.group(1)
            current_heading = m.group(2).strip()
            current_body = []
            continue

        # Setext heading (underline with === or ---)
        if i > 0 and re.match(r"^[=]{3,}$", line.strip()):
            body_without_last = current_body[:-1] if current_body else []
            title_line = current_body[-1] if current_body else ""
            if current_heading or body_without_last:
                sections.append((current_marker, current_heading, body_without_last))
            current_marker = "#"
            current_heading = title_line.strip()
            current_body = []
            continue
        if i > 0 and re.match(r"^[-]{3,}$", line.strip()):
            body_without_last = current_body[:-1] if current_body else []
            title_line = current_body[-1] if current_body else ""
            if current_heading or body_without_last:
                sections.append((current_marker, current_heading, body_without_last))
            current_marker = "##"
            current_heading = title_line.strip()
            current_body = []
            continue

        current_body.append(line)

    if current_heading or current_body:
        sections.append((current_marker, current_heading, current_body))

    return sections


def _sections_to_articles(
    sections: list[tuple[str, str, list[str]]],
) -> list[Article]:
    """Convert heading-based sections to Articles.

    Top-level headings (# or ##) become chapters.
    Lower headings (### and below) become articles within chapters.
    """
    articles: list[Article] = []
    current_chapter = ""
    current_chapter_title = ""
    article_counter = 0

    for marker, heading, body_lines in sections:
        level = len(marker) if marker.startswith("#") else 1
        body_text = "\n".join(body_lines).strip()

        if level <= 2:
            # Chapter-level heading
            current_chapter_title = heading
            # Try to extract number
            m = re.match(r"(\d+(?:\.\d+)*)\s*[.:\-–—]\s*(.*)", heading)
            if m:
                current_chapter = m.group(1)
                current_chapter_title = m.group(2) or heading
            else:
                current_chapter = str(level)
            # If there's body text under a chapter heading, treat it as an article
            if body_text:
                article_counter += 1
                paragraphs = _parse_paragraphs(body_text)
                articles.append(
                    Article(
                        number=str(article_counter),
                        title=heading,
                        chapter=current_chapter,
                        chapter_title=current_chapter_title,
                        paragraphs=paragraphs,
                        full_text=body_text,
                    )
                )
        else:
            # Article-level heading
            article_counter += 1
            # Try to extract article number from heading
            m = re.match(r"(?:Art(?:icle|ikel)?\.?\s*)?(\d+(?:\.\d+)*)\s*[.:\-–—]?\s*(.*)", heading)
            if m:
                number = m.group(1)
                title = m.group(2) or heading
            else:
                number = str(article_counter)
                title = heading

            paragraphs = _parse_paragraphs(body_text) if body_text else ()
            articles.append(
                Article(
                    number=number,
                    title=title,
                    chapter=current_chapter,
                    chapter_title=current_chapter_title,
                    paragraphs=paragraphs,
                    full_text=body_text,
                )
            )

    return articles


class HtmlPageSource:
    """Load a normative document from a single HTML page."""

    def __init__(
        self,
        url_or_html: str,
        *,
        title: str = "",
        language: str = "",
        is_html: bool = False,
    ) -> None:
        self._source = url_or_html
        self._title = title
        self._language = language
        self._is_html = is_html

    def fetch(self) -> NormativeDocument:
        if self._is_html:
            html = self._source
            source = "<html-string>"
        elif self._source.startswith(("http://", "https://")):
            html = _http_get(self._source)
            source = self._source
        else:
            html = Path(self._source).read_text(encoding="utf-8")
            source = self._source

        parsed = _parse_html(html)
        text = parsed.text

        # Detect title from headings if not provided
        title = self._title
        if not title and parsed.headings:
            title = parsed.headings[0][1]

        # Detect chapters from heading hierarchy
        chapter_map = _detect_chapters(parsed.headings)

        # Parse articles from text
        articles = _text_to_articles(text, source_url=source)

        # Enrich articles with chapter info from headings
        enriched: list[Article] = []
        for art in articles:
            if art.title in chapter_map:
                ch_num, ch_title = chapter_map[art.title]
                art = Article(
                    number=art.number,
                    title=art.title,
                    chapter=ch_num,
                    chapter_title=ch_title,
                    paragraphs=art.paragraphs,
                    full_text=art.full_text,
                    url=art.url,
                )
            enriched.append(art)

        return NormativeDocument(
            title=title,
            source=source,
            articles=tuple(enriched or articles),
            language=self._language,
        )


class HtmlIndexSource:
    """Load from an index page that links to individual article pages.

    Fetches the index page, extracts article links matching a pattern,
    then fetches each article page.
    """

    def __init__(
        self,
        index_url: str,
        *,
        link_pattern: str = "",
        title: str = "",
        language: str = "",
        rate_limit: float = _RATE_LIMIT_DELAY,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self._index_url = index_url
        self._link_pattern = re.compile(link_pattern) if link_pattern else None
        self._title = title
        self._language = language
        self._rate_limit = rate_limit
        self._timeout = timeout

    def fetch(self) -> NormativeDocument:
        # Fetch index page
        html = _http_get(self._index_url, timeout=self._timeout)
        parsed = _parse_html(html)

        title = self._title
        if not title and parsed.headings:
            title = parsed.headings[0][1]

        # Extract article links
        article_links = self._extract_article_links(parsed.links)
        logger.info("Found %d article links on index page", len(article_links))

        # Fetch each article
        articles: list[Article] = []
        for idx, (url, link_text) in enumerate(article_links):
            try:
                if idx > 0 and self._rate_limit > 0:
                    time.sleep(self._rate_limit)
                art_html = _http_get(url, timeout=self._timeout)
                art_parsed = _parse_html(art_html)
                art_text = art_parsed.text

                # Try to get article title from page headings
                art_title = ""
                if art_parsed.headings:
                    art_title = art_parsed.headings[0][1]
                if not art_title:
                    art_title = link_text

                # Parse article number from title or URL
                number = _extract_article_number(art_title, url)

                paragraphs = _parse_paragraphs(art_text)
                articles.append(
                    Article(
                        number=number,
                        title=art_title,
                        chapter="",
                        chapter_title="",
                        paragraphs=paragraphs,
                        full_text=art_text.strip(),
                        url=url,
                    )
                )
                logger.info("Fetched article %s: %s", number, art_title[:60])
            except Exception:
                logger.warning("Failed to fetch %s, skipping", url, exc_info=True)

        return NormativeDocument(
            title=title or "Untitled",
            source=self._index_url,
            articles=tuple(articles),
            language=self._language,
        )

    def _extract_article_links(
        self, links: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """Filter and de-duplicate article links."""
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        for href, text in links:
            full_url = urljoin(self._index_url, href)
            if full_url in seen:
                continue
            if self._link_pattern and not self._link_pattern.search(full_url):
                continue
            # Skip anchors, mailto, javascript
            parsed = urlparse(full_url)
            if parsed.scheme not in ("http", "https"):
                continue
            seen.add(full_url)
            result.append((full_url, text))
        return result


def _extract_article_number(title: str, url: str) -> str:
    """Extract article/section number from title or URL."""
    # Try title first: "Art. 17 ..." or "Article 17 ..."
    m = re.search(r"Art(?:icle)?\.?\s*(\d+)", title, re.IGNORECASE)
    if m:
        return m.group(1)
    # Try "Section 5.2"
    m = re.search(r"Section\s+(\d+(?:\.\d+)*)", title, re.IGNORECASE)
    if m:
        return m.group(1)
    # Try "§ 42"
    m = re.search(r"§\s*(\d+[a-z]?)", title)
    if m:
        return m.group(1)
    # Try URL: .../art-17-gdpr/ or .../section-5/
    m = re.search(r"art(?:icle)?[_-](\d+)", url, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"section[_-](\d+(?:[_-]\d+)*)", url, re.IGNORECASE)
    if m:
        return m.group(1).replace("-", ".").replace("_", ".")
    return "?"


# ── Public API ──────────────────────────────────────────────────────


def detect_source_type(source: str) -> str:
    """Auto-detect the source type from a URL or file path.

    Returns one of: "html-index", "html", "text", "pdf", "unknown".
    """
    if source.startswith(("http://", "https://")):
        parsed = urlparse(source)
        path_lower = parsed.path.lower()
        if path_lower.endswith(".pdf"):
            return "pdf"
        if path_lower.endswith((".txt", ".md")):
            return "text"
        # Heuristic: paths ending in / or containing index/topics
        # are likely index pages
        if any(kw in path_lower for kw in ("/topics", "/index", "/toc")):
            return "html-index"
        if path_lower.endswith("/") and not path_lower.rstrip("/").endswith(
            (".html", ".htm")
        ):
            return "html-index"
        return "html"

    # Local file
    p = Path(source)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in (".html", ".htm"):
        return "html"
    if suffix in (".txt", ".md", ".rst", ".adoc"):
        return "text"
    return "unknown"


def fetch_document(
    source: str,
    *,
    source_type: str = "auto",
    title: str = "",
    language: str = "",
    link_pattern: str = "",
    rate_limit: float = _RATE_LIMIT_DELAY,
) -> NormativeDocument:
    """Fetch a normative document from any supported source.

    Args:
        source: URL or local file path.
        source_type: One of "auto", "html", "html-index", "text", "pdf".
            "auto" detects from URL/path.
        title: Document title override.
        language: Language hint ("en" or "" for the default profile).
        link_pattern: Regex to filter article links (html-index only).
        rate_limit: Seconds between HTTP requests (html-index only).

    Returns:
        NormativeDocument with parsed articles.

    Raises:
        ValueError: If source_type is unsupported.
        FileNotFoundError: If local file does not exist.
        urllib.error.URLError: If HTTP fetch fails.
    """
    if source_type == "auto":
        source_type = detect_source_type(source)

    if source_type == "text":
        return PlainTextSource(source, title=title, language=language).fetch()
    if source_type == "html":
        return HtmlPageSource(source, title=title, language=language).fetch()
    if source_type == "html-index":
        return HtmlIndexSource(
            source,
            title=title,
            language=language,
            link_pattern=link_pattern,
            rate_limit=rate_limit,
        ).fetch()
    if source_type == "pdf":
        raise ValueError(
            "PDF support requires an optional dependency. "
            "Install with: pip install pymupdf"
        )
    raise ValueError(f"Unsupported source_type: {source_type!r}")
