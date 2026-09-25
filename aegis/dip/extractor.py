"""Stage 3: LLM-based normative statement extraction.

Extracts structured normative statements from NormativeChunks using
an LLM with structured tool calls. Processes chunks in batches for
efficiency.

Domain-agnostic: the ``domain_context`` parameter provides domain hints
to the LLM at runtime.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aegis.dip.models import ChunkType, NormativeChunk, NormativeStatement
from aegis.dip.prompts import (
    EXTRACT_STATEMENT_TOOL,
    build_extractor_system_prompt,
    build_extractor_user_message,
)
from aegis.editor.llm_provider import LLMClient

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 5


def extract_statements(
    chunks: list[NormativeChunk],
    client: LLMClient,
    *,
    domain_context: str = "",
    batch_size: int = _DEFAULT_BATCH_SIZE,
    on_progress: Any | None = None,
) -> list[NormativeStatement]:
    """Extract normative statements from chunks via LLM.

    Args:
        chunks: Classified normative chunks from the chunker.
        client: LLM client for API calls.
        domain_context: Domain-specific hints for the LLM.
        batch_size: Number of chunks per LLM call.
        on_progress: Optional callback ``(batch_index, total_batches, statements_so_far)``.

    Returns:
        List of extracted NormativeStatements with source references.
    """
    # Filter out non-extractable chunk types
    extractable = [
        c for c in chunks
        if c.chunk_type not in (ChunkType.ORGANIZATIONAL, ChunkType.DEFINITION)
    ]

    if not extractable:
        logger.info("No extractable chunks — skipping extraction")
        return []

    system_prompt = build_extractor_system_prompt(domain_context=domain_context)
    all_statements: list[NormativeStatement] = []

    # Process in batches
    batches = _make_batches(extractable, batch_size)
    total_batches = len(batches)

    for batch_idx, batch in enumerate(batches):
        logger.info(
            "Extracting batch %d/%d (%d chunks)",
            batch_idx + 1,
            total_batches,
            len(batch),
        )

        chunk_dicts = [
            {
                "article_ref": c.article_ref,
                "text": c.text,
                "chunk_type": c.chunk_type.value,
            }
            for c in batch
        ]

        user_message = build_extractor_user_message(chunk_dicts)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Build ref→text lookup for this batch
        ref_to_text = {c.article_ref: c.text for c in batch}

        try:
            response = client.chat(messages, tools=[EXTRACT_STATEMENT_TOOL])
            batch_statements = _parse_extraction_response(response)
            # Enrich with original text from chunks
            batch_statements = _enrich_original_text(batch_statements, ref_to_text)
            all_statements.extend(batch_statements)
            logger.info(
                "Batch %d/%d: extracted %d statements",
                batch_idx + 1,
                total_batches,
                len(batch_statements),
            )
        except Exception:
            logger.warning(
                "Batch %d/%d failed, skipping",
                batch_idx + 1,
                total_batches,
                exc_info=True,
            )

        if on_progress:
            on_progress(batch_idx + 1, total_batches, len(all_statements))

    logger.info("Extraction complete: %d statements from %d chunks", len(all_statements), len(extractable))
    return all_statements


def _make_batches(
    items: list[NormativeChunk],
    batch_size: int,
) -> list[list[NormativeChunk]]:
    """Split items into batches of at most batch_size."""
    return [
        items[i : i + batch_size]
        for i in range(0, len(items), batch_size)
    ]


def _parse_extraction_response(
    response: dict[str, Any],
) -> list[NormativeStatement]:
    """Parse LLM response into NormativeStatements.

    Tolerant: skips malformed tool calls with a warning.
    """
    statements: list[NormativeStatement] = []
    message = response.get("choices", [{}])[0].get("message", {})
    tool_calls = message.get("tool_calls", [])

    for tc in tool_calls:
        fn = tc.get("function", {})
        if fn.get("name") != "extract_normative_statement":
            continue

        try:
            raw_args = fn.get("arguments", "{}")
            args: dict[str, Any] = (
                json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            )
            stmt = _args_to_statement(args)
            statements.append(stmt)
        except Exception:
            logger.warning("Skipping malformed tool call: %s", fn, exc_info=True)

    return statements


def _enrich_original_text(
    statements: list[NormativeStatement],
    ref_to_text: dict[str, str],
) -> list[NormativeStatement]:
    """Set original_text on statements from chunk text lookup."""
    enriched = []
    for stmt in statements:
        if not stmt.original_text and stmt.source_article in ref_to_text:
            # Frozen dataclass → reconstruct with original_text
            stmt = NormativeStatement(
                source_article=stmt.source_article,
                modality=stmt.modality,
                subject=stmt.subject,
                action=stmt.action,
                object_description=stmt.object_description,
                conditions=stmt.conditions,
                exceptions=stmt.exceptions,
                vague_terms=stmt.vague_terms,
                confidence=stmt.confidence,
                original_text=ref_to_text[stmt.source_article],
            )
        enriched.append(stmt)
    return enriched


def _args_to_statement(args: dict[str, Any]) -> NormativeStatement:
    """Convert tool call arguments to a NormativeStatement."""
    return NormativeStatement(
        source_article=args.get("source_ref", ""),
        modality=args.get("modality", "OBLIGATORY"),
        subject=args.get("subject", ""),
        action=args.get("action", ""),
        object_description=args.get("object_description", ""),
        conditions=tuple(args.get("conditions", ())),
        exceptions=tuple(args.get("exceptions", ())),
        vague_terms=tuple(args.get("vague_terms", ())),
        confidence=float(args.get("confidence", 1.0)),
        original_text=args.get("original_text", ""),
    )
