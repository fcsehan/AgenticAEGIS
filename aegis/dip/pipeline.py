"""DIP pipeline orchestrator — stages 1 through 6.

Orchestrates the full document intelligence pipeline from source
document to exported MELD domain. Stages 1-2 are deterministic,
stages 3-4 require an LLM client, stages 5-6 are deterministic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from aegis.dip.chunker import chunk_document
from aegis.dip.coexistence import validate_output_target
from aegis.dip.domain_exporter import export_domain
from aegis.dip.extractor import extract_statements
from aegis.dip.fetcher import fetch_document
from aegis.dip.models import (
    DomainExport,
    NormativeChunk,
    NormativeDocument,
    NormativeStatement,
    DomainOntology,
)
from aegis.dip.ontology_builder import build_ontology
from aegis.dip.rule_compiler import compile_rules
from aegis.editor.llm_provider import LLMClient

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]  # (stage_number, message)


def run_pipeline(
    source: str,
    name: str,
    client: LLMClient,
    output_dir: str | Path,
    *,
    source_type: str = "auto",
    language: str = "auto",
    domain_context: str = "",
    batch_size: int = 5,
    confidence_threshold: float = 0.7,
    verify: bool = False,
    on_progress: ProgressCallback | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> DomainExport:
    """Run the full 6-stage DIP pipeline.

    Args:
        source: URL or file path to the normative document.
        name: Domain name for the exported files.
        client: LLM client for stages 3 and 4.
        output_dir: Directory for exported MELD files.
        source_type: Source type hint (auto, html, html-index, text, pdf).
        language: Language hint for the chunker (auto or en).
        domain_context: Domain-specific hints for the LLM.
        batch_size: Chunks per LLM call in stage 3.
        confidence_threshold: Flag statements below this confidence.
        on_progress: Optional callback for progress reporting.
        dry_run: If True, skip file export (stage 6).
        force: If True, override soft coexistence conflicts (existing .meld
            files in output_dir). Hard conflicts (writing into a manually
            authored domain path) remain refused even with force=True.

    Returns:
        DomainExport with paths, statistics, and review flags.

    Raises:
        DomainCoexistenceError: when ``output_dir`` collides with a manual
            domain or contains existing .meld files without ``force=True``.
            See ``aegis/dip/coexistence.py`` and decision D-015.
    """
    output = Path(output_dir)
    if not dry_run:
        validate_output_target(output, name, force=force)
    _progress(on_progress, 1, "Loading document...")

    # ── Stage 1: Fetch ──────────────────────────────────────────
    doc = fetch_document(source, source_type=source_type, language=language)
    _progress(
        on_progress, 1,
        f"Loaded '{doc.title}': {len(doc.articles)} articles",
    )

    # ── Stage 2: Chunk ──────────────────────────────────────────
    _progress(on_progress, 2, "Chunking document...")
    chunks = chunk_document(doc, language=language)
    _progress(
        on_progress, 2,
        f"Produced {len(chunks)} normative chunks",
    )

    # ── Stage 3: Extract ────────────────────────────────────────
    _progress(on_progress, 3, "Extracting normative statements...")
    statements = extract_statements(
        chunks,
        client,
        domain_context=domain_context,
        batch_size=batch_size,
        on_progress=lambda b, t, s: _progress(
            on_progress, 3,
            f"Batch {b}/{t} — {s} statements so far",
        ),
    )
    _progress(
        on_progress, 3,
        f"Extracted {len(statements)} normative statements",
    )

    # ── Stage 4: Ontology ───────────────────────────────────────
    _progress(on_progress, 4, "Deriving domain ontology...")
    ontology = build_ontology(
        statements,
        client,
        domain_context=domain_context,
    )
    _progress(
        on_progress, 4,
        f"Ontology: {len(ontology.roles)} roles, "
        f"{len(ontology.actions)} actions, "
        f"{len(ontology.data_categories)} categories",
    )

    # ── Stage 5: Compile ────────────────────────────────────────
    _progress(on_progress, 5, f"Compiling rules{' + verifying' if verify else ''}...")
    results = compile_rules(
        statements,
        ontology,
        confidence_threshold=confidence_threshold,
        verify=verify,
    )
    ok = sum(1 for r in results if r.success)
    flagged = sum(1 for r in results if r.flagged)
    _progress(
        on_progress, 5,
        f"Compiled {ok} rules ({flagged} flagged for review)",
    )

    # ── Stage 6: Export ─────────────────────────────────────────
    if dry_run:
        _progress(on_progress, 6, "Dry run — skipping file export")
        return DomainExport(
            domain_name=name,
            total_rules=ok,
            auto_generated=ok - flagged,
            flagged_for_review=flagged,
            articles_processed=len({r.source_article for r in results}),
            obligations=sum(1 for r in results if r.success and "oughtToDo" in r.meld_expression),
            prohibitions=sum(1 for r in results if r.success and "forbiddenToDo" in r.meld_expression),
            permissions=sum(1 for r in results if r.success and "permittedToDo" in r.meld_expression and "forbiddenToDo" not in r.meld_expression),
        )

    _progress(on_progress, 6, "Exporting MELD domain...")
    export = export_domain(name, ontology, results, output)
    _progress(on_progress, 6, export.summary())

    return export


def _progress(
    callback: ProgressCallback | None,
    stage: int,
    message: str,
) -> None:
    """Report progress via callback and logger."""
    full_msg = f"[Stage {stage}/6] {message}"
    logger.info(full_msg)
    if callback:
        callback(stage, message)
