"""Stage 2: Generic chunker with configurable signal-word profiles.

Classifies paragraphs/sections of a normative document by their deontic
function (obligation, prohibition, permission, exception, definition,
organizational). The classification is based on configurable signal-word
profiles per language.

The chunker is domain-agnostic — language-specific signal words are
encapsulated in ``SignalWordProfile`` instances.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from aegis.dip.fetcher import extract_cross_refs
from aegis.dip.models import (
    Article,
    ChunkType,
    NormativeChunk,
    NormativeDocument,
    Paragraph,
)


# ── Signal Word Profiles ────────────────────────────────────────────


@dataclass(frozen=True)
class SignalWordProfile:
    """Language-specific signal words for deontic classification.

    Each field contains regex patterns (case-insensitive) that indicate
    the deontic function of a normative text fragment.
    """

    language: str
    obligation: tuple[str, ...] = ()
    prohibition: tuple[str, ...] = ()
    permission: tuple[str, ...] = ()
    exception: tuple[str, ...] = ()
    definition: tuple[str, ...] = ()
    organizational_chapter_patterns: tuple[str, ...] = ()



PROFILE_EN = SignalWordProfile(
    language="en",
    obligation=(
        r"\bshall\b",
        r"\bmust\b",
        r"\bis\s+required\s+to\b",
        r"\bare\s+required\s+to\b",
        r"\bhas\s+(?:a\s+)?duty\s+to\b",
        r"\bis\s+obligat(?:ed|ory)\b",
        r"\bshall\s+ensure\b",
        r"\bmust\s+ensure\b",
        r"\bis\s+responsible\s+for\b",
        r"\bmust\s+be\b",
        r"\bshall\s+be\b",
    ),
    prohibition=(
        r"\bshall\s+not\b",
        r"\bmust\s+not\b",
        r"\bis\s+prohibited\b",
        r"\bare\s+prohibited\b",
        r"\bis\s+forbidden\b",
        r"\bare\s+forbidden\b",
        r"\bmay\s+not\b",
        r"\bis\s+not\s+permitted\b",
        r"\bis\s+not\s+allowed\b",
    ),
    permission=(
        r"\bmay\b(?!\s+not)",
        r"\bis\s+permitted\b",
        r"\bare\s+permitted\b",
        r"\bis\s+entitled\b",
        r"\bare\s+entitled\b",
        r"\bhas\s+the\s+right\b",
        r"\bhave\s+the\s+right\b",
        r"\bis\s+allowed\b",
        r"\bare\s+allowed\b",
        r"\bcan\b",
    ),
    exception=(
        r"\bdoes\s+not\s+apply\b",
        r"\bdo\s+not\s+apply\b",
        r"\bshall\s+not\s+apply\b",
        r"\bunless\b",
        r"\bnotwithstanding\b",
        r"\bexcept\s+(?:where|when|if)\b",
        r"\bwithout\s+prejudice\b",
        r"\bsubject\s+to\b",
        r"\bprovided\s+that\b",
        r"\bsave\s+(?:where|for)\b",
    ),
    definition=(
        r"\bmeans\b",
        r"\brefers?\s+to\b",
        r"\bfor\s+the\s+purposes?\s+of\b",
        r"\bas\s+defined\s+in\b",
        r"\bdefinition\b",
    ),
    organizational_chapter_patterns=(
        r"(?i)\bgeneral\s+provisions?\b",
        r"(?i)\bfinal\s+provisions?\b",
        r"(?i)\btransitional\b",
        r"(?i)\bentry\s+into\s+force\b",
        r"(?i)\bsupervisory\s+authorit\b",
        r"(?i)\bremedies?\b",
        r"(?i)\bpenalt(?:y|ies)\b",
        r"(?i)\benforcement\b",
    ),
)

_PROFILES: dict[str, SignalWordProfile] = {
    "en": PROFILE_EN,
}


# ── Language detection ──────────────────────────────────────────────

def detect_language(text: str) -> str:
    """Select the default input profile.

    The auto mode selects English; it does not infer another language.
    """
    return "en"


def get_profile(language: str) -> SignalWordProfile:
    """Get signal word profile for a language. Falls back to English."""
    return _PROFILES.get(language, PROFILE_EN)


# ── Classification engine ───────────────────────────────────────────


def _classify_text(text: str, profile: SignalWordProfile) -> ChunkType:
    """Classify a text fragment by its deontic function.

    Priority order (highest to lowest):
    1. EXCEPTION — trumps everything (it modifies other norms)
    2. DEFINITION — structural, not deontic
    3. PROHIBITION — stronger than obligation/permission
    4. OBLIGATION
    5. PERMISSION
    6. UNKNOWN — no signal word matched
    """
    scores: dict[ChunkType, int] = {
        ChunkType.OBLIGATION: 0,
        ChunkType.PROHIBITION: 0,
        ChunkType.PERMISSION: 0,
        ChunkType.EXCEPTION: 0,
        ChunkType.DEFINITION: 0,
    }

    for pattern in profile.exception:
        if re.search(pattern, text, re.IGNORECASE):
            scores[ChunkType.EXCEPTION] += 2  # higher weight

    for pattern in profile.definition:
        if re.search(pattern, text, re.IGNORECASE):
            scores[ChunkType.DEFINITION] += 2

    for pattern in profile.prohibition:
        if re.search(pattern, text, re.IGNORECASE):
            scores[ChunkType.PROHIBITION] += 1

    for pattern in profile.obligation:
        if re.search(pattern, text, re.IGNORECASE):
            scores[ChunkType.OBLIGATION] += 1

    for pattern in profile.permission:
        if re.search(pattern, text, re.IGNORECASE):
            scores[ChunkType.PERMISSION] += 1

    # Pick highest score; priority order for ties
    priority = [
        ChunkType.EXCEPTION,
        ChunkType.DEFINITION,
        ChunkType.PROHIBITION,
        ChunkType.OBLIGATION,
        ChunkType.PERMISSION,
    ]
    best_score = max(scores.values())
    if best_score == 0:
        return ChunkType.UNKNOWN

    for ct in priority:
        if scores[ct] == best_score:
            return ct

    return ChunkType.UNKNOWN  # unreachable


def _is_organizational(
    article: Article,
    profile: SignalWordProfile,
) -> bool:
    """Check if an article is organizational (non-normative).

    Only filters articles whose own title matches organizational patterns.
    Chapter titles alone do not cause filtering — a "Definitions" article
    inside a "General Provisions" chapter is still valuable.
    """
    # Check article title only (not chapter title)
    for pattern in profile.organizational_chapter_patterns:
        if re.search(pattern, article.title, re.IGNORECASE):
            return True
    return False


# ── Reference patterns ──────────────────────────────────────────────


def _build_article_ref(article: Article, paragraph: Paragraph | None = None) -> str:
    """Build a human-readable reference like 'Art. 17(1)' or 'Section 5.2'."""
    # Detect reference style from article number
    number = article.number
    if re.match(r"\d+\.\d+", number):
        # ISO-style: Section 5.2
        ref = f"Section {number}"
    elif re.match(r"[A-Z]", number):
        # Annex-style: Clause A.5.1
        ref = f"Clause {number}"
    else:
        # Law-style: Art. 17
        ref = f"Art. {number}"

    if paragraph and paragraph.number:
        ref += f"({paragraph.number})"

    return ref


def _find_parent_ref(
    article: Article,
    paragraph: Paragraph,
    chunk_type: ChunkType,
) -> str:
    """Find the parent reference for an exception chunk.

    Heuristic: an exception in paragraph N refers to paragraph 1 of the
    same article (the main provision).
    """
    if chunk_type != ChunkType.EXCEPTION:
        return ""
    if paragraph.number and paragraph.number != "1":
        return _build_article_ref(article, Paragraph(number="1", text=""))
    return ""


# ── Public API ──────────────────────────────────────────────────────


def chunk_document(
    doc: NormativeDocument,
    *,
    profile: SignalWordProfile | None = None,
    language: str = "auto",
) -> list[NormativeChunk]:
    """Chunk a normative document into classified fragments.

    Args:
        doc: The document to chunk.
        profile: Signal word profile. If None, auto-detected from language.
        language: Language hint ("en" or "auto").

    Returns:
        List of NormativeChunks, one per normative paragraph.
        Non-normative (organizational) articles are filtered out.
    """
    if profile is None:
        if language == "auto":
            # Detect from document content
            all_text = " ".join(
                p.text for a in doc.articles for p in a.paragraphs
            )
            if not all_text:
                all_text = " ".join(a.full_text for a in doc.articles)
            lang = doc.language or detect_language(all_text)
        else:
            lang = language
        profile = get_profile(lang)

    chunks: list[NormativeChunk] = []

    for article in doc.articles:
        # Filter organizational articles
        if _is_organizational(article, profile):
            continue

        if article.paragraphs:
            # Chunk per paragraph
            for para in article.paragraphs:
                ref = _build_article_ref(article, para)
                chunk_type = _classify_text(para.text, profile)

                # Organizational paragraphs within normative articles → skip
                if chunk_type == ChunkType.ORGANIZATIONAL:
                    continue

                parent_ref = _find_parent_ref(article, para, chunk_type)
                cross_refs = extract_cross_refs(para.text)

                chunks.append(
                    NormativeChunk(
                        article_ref=ref,
                        text=para.text,
                        chunk_type=chunk_type,
                        parent_ref=parent_ref,
                        cross_refs=cross_refs,
                        article_title=article.title,
                    )
                )
        elif article.full_text:
            # No paragraph structure — chunk entire article
            ref = _build_article_ref(article)
            chunk_type = _classify_text(article.full_text, profile)
            cross_refs = extract_cross_refs(article.full_text)

            chunks.append(
                NormativeChunk(
                    article_ref=ref,
                    text=article.full_text,
                    chunk_type=chunk_type,
                    cross_refs=cross_refs,
                    article_title=article.title,
                )
            )

    return chunks
