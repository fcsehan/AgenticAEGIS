"""Data models for all DIP pipeline stages.

Immutable dataclasses representing the intermediate artifacts as a
normative document flows through the 6-stage pipeline:

  NormativeDocument → NormativeChunk → NormativeStatement
  → DomainOntology → (RuleProposal from aegis.editor) → DomainExport

DIP is domain-agnostic: these models work for any normative document
(laws, regulations, standards, corporate policies, codes of conduct).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ── Stage 1: Fetcher output ─────────────────────────────────────────


@dataclass(frozen=True)
class Paragraph:
    """A single paragraph or sub-section within an article/section."""

    number: str  # "1", "2", "3" or "" if unnumbered
    text: str
    litera: list[str] = field(default_factory=list)  # ["a", "b", "c"] sub-items


@dataclass(frozen=True)
class Article:
    """A single article/section/clause of a normative document.

    Named 'Article' because it is the standard term in EU regulations,
    ISO standards, and NATO STANAGs. For documents that use 'Section'
    or 'Clause', the mapping is: Section/Clause → Article.
    """

    number: str  # "6", "17", "A.5.1"
    title: str  # "Lawfulness of processing" / "Access control"
    chapter: str  # "II", "A.5" or "" if flat
    chapter_title: str  # "Principles" / "Organizational controls"
    paragraphs: tuple[Paragraph, ...] = ()
    full_text: str = ""  # raw text for fallback
    url: str = ""  # source URL if fetched


@dataclass(frozen=True)
class NormativeDocument:
    """A complete normative document with all its articles/sections.

    Covers any document type containing obligations, prohibitions, or
    permissions: laws, regulations, standards, corporate policies,
    codes of conduct, engagement rules.
    """

    title: str  # "GDPR" / "ISO 27001" / "Corporate Code of Conduct"
    source: str  # URL, file path, or description of origin
    articles: tuple[Article, ...] = ()
    language: str = ""  # "en" or "" for the default profile
    metadata: dict[str, str] = field(default_factory=dict)


# ── Stage 2: Chunker output ─────────────────────────────────────────


class ChunkType(Enum):
    """Classification of a normative chunk by its deontic function."""

    OBLIGATION = "obligation"  # "must", "shall", "is required to"
    PROHIBITION = "prohibition"  # "must not", "shall not", "is prohibited"
    PERMISSION = "permission"  # "may", "is entitled to", "has the right"
    EXCEPTION = "exception"  # "does not apply", "unless", "notwithstanding"
    DEFINITION = "definition"  # "means", "refers to", "for the purposes of"
    ORGANIZATIONAL = "organizational"  # procedural, administrative
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NormativeChunk:
    """A classified fragment of a normative document."""

    article_ref: str  # "Art. 17(1)" / "Section 5.2" / "Clause A.5.1"
    text: str  # the normative text
    chunk_type: ChunkType
    parent_ref: str = ""  # what an exception refers to
    cross_refs: tuple[str, ...] = ()  # referenced articles/sections
    article_title: str = ""


# ── Stage 3: Extractor output ───────────────────────────────────────


@dataclass(frozen=True)
class NormativeStatement:
    """A structured normative assertion extracted by the LLM."""

    source_article: str  # "Art. 17(1)" / "Section 5.2"
    modality: str  # "OBLIGATORY" | "FORBIDDEN" | "PERMITTED"
    subject: str  # "data controller" (natural language)
    action: str  # "deletion of personal data"
    object_description: str = ""  # "upon request of the data subject"
    conditions: tuple[str, ...] = ()  # triggering conditions
    exceptions: tuple[str, ...] = ()  # references to exception articles
    vague_terms: tuple[str, ...] = ()  # "without undue delay", "appropriate"
    confidence: float = 1.0  # LLM confidence 0.0-1.0
    original_text: str = ""  # source text for traceability


# ── Stage 4: Ontology Builder output ────────────────────────────────


@dataclass(frozen=True)
class OntologyRole:
    """A domain role derived from the normative document."""

    natural_name: str  # "data controller" / "commander"
    meld_symbol: str  # "dataController" / "commander"
    description: str = ""


@dataclass(frozen=True)
class OntologyAction:
    """A domain action type with its parameters."""

    natural_name: str  # "deletion of personal data" / "share intelligence"
    meld_symbol: str  # "deleteData" / "shareIntelligence"
    parameters: tuple[str, ...] = ()  # ("dataCategory",)
    description: str = ""


@dataclass(frozen=True)
class DomainOntology:
    """Complete domain ontology derived from normative statements."""

    roles: tuple[OntologyRole, ...] = ()
    actions: tuple[OntologyAction, ...] = ()
    data_categories: tuple[str, ...] = ()  # MELD symbols
    legal_bases: tuple[str, ...] = ()  # consent, contract, ...
    role_hierarchy: tuple[tuple[str, str], ...] = ()  # (child, parent) genls pairs
    codes: tuple[str, ...] = ("DataProtection",)
    # Mapping from natural language to MELD symbols
    role_map: dict[str, str] = field(default_factory=dict)
    action_map: dict[str, str] = field(default_factory=dict)


# ── Stage 5: Rule Compiler output ───────────────────────────────────
# Uses RuleProposal from aegis.editor.meld_generator (no duplication)


@dataclass(frozen=True)
class CompilationResult:
    """Result of compiling a NormativeStatement into a RuleProposal."""

    source_article: str
    success: bool
    meld_expression: str = ""
    error: str = ""
    flagged: bool = False  # needs human review
    flag_reason: str = ""  # why flagged
    source_text: str = ""  # original text from the normative document
    natural_language_summary: str = ""  # human-readable rule summary


# ── Stage 6: Domain Export output ───────────────────────────────────


@dataclass(frozen=True)
class ReviewFlag:
    """A flag for human review on a generated rule."""

    article_ref: str
    rule_index: int
    reason: str  # "vague_term" | "delegation_clause" | "low_confidence" | "unmapped_term"
    detail: str  # specific term or clause
    meld_expression: str = ""


@dataclass(frozen=True)
class DomainExport:
    """Result of the full DIP pipeline."""

    domain_name: str
    ontology_path: str = ""
    vocab_path: str = ""
    rules_path: str = ""
    total_rules: int = 0
    auto_generated: int = 0
    flagged_for_review: int = 0
    flags: tuple[ReviewFlag, ...] = ()
    articles_processed: int = 0
    articles_skipped: int = 0
    obligations: int = 0
    prohibitions: int = 0
    permissions: int = 0

    def summary(self) -> str:
        """Human-readable summary of the export."""
        return (
            f"Domain '{self.domain_name}': {self.total_rules} rules "
            f"({self.obligations} OBL, {self.prohibitions} FRB, {self.permissions} PRM), "
            f"{self.auto_generated} auto-generated, "
            f"{self.flagged_for_review} flagged for review, "
            f"from {self.articles_processed} articles "
            f"({self.articles_skipped} skipped)"
        )
