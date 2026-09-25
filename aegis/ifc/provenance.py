"""AEGIS-1703: Provenance-Carrying Tool Results.

Every piece of content returned through the retrieval broker carries
machine-readable provenance: source path, classification, canary tokens,
and access constraints.  The taint tracker ingests these records to
maintain session-level information flow state.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Provenance metadata for a single information source.

    Attributes:
        source_path: File or resource path where the content originated.
        classification: Classification level (e.g. "public", "secret").
        canary_tokens: Sensitive tokens embedded in the source for leak detection.
        allowed_recipients: Recipient identifiers permitted to receive this content.
        allowed_purposes: Purpose categories for which access is granted.
    """

    source_path: str
    classification: str
    canary_tokens: tuple[str, ...] = ()
    allowed_recipients: tuple[str, ...] = ()
    allowed_purposes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProvenancedResult:
    """A tool result with attached provenance metadata.

    Attributes:
        content: The (possibly empty or redacted) content string.
        provenance: One record per source that contributed to this result.
        redacted: Whether the content was redacted before delivery.
        response_mode: How the broker resolved this request:
            ``"deny"`` — access forbidden, no content returned.
            ``"metadata-only"`` — only file metadata, no content.
            ``"redacted-snippet"`` — content with sensitive parts removed.
            ``"full-content"`` — unmodified content returned.
        derived_from: Source paths of upstream results this was derived from.
    """

    content: str
    provenance: tuple[ProvenanceRecord, ...]
    redacted: bool = False
    response_mode: str = "full-content"
    derived_from: tuple[str, ...] = ()
