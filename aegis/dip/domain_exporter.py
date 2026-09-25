"""Stage 6: Domain exporter — 3 MELD files + review report.

Exports the compiled domain as three MELD files (ontology, action vocab,
deontic rules) plus a machine-readable review report (JSON).

Domain-agnostic: the domain name is freely chosen by the user.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from aegis.dip.models import (
    CompilationResult,
    DomainExport,
    DomainOntology,
    ReviewFlag,
)

logger = logging.getLogger(__name__)


def export_domain(
    name: str,
    ontology: DomainOntology,
    results: list[CompilationResult],
    output_dir: Path,
) -> DomainExport:
    """Export a compiled domain as 3 MELD files + review report.

    Args:
        name: Domain name (e.g. "gdpr", "corporate-policy").
        ontology: The derived domain ontology.
        results: Compilation results from the rule compiler.
        output_dir: Directory to write files to.

    Returns:
        DomainExport with paths, statistics, and review flags.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pascal = _pascal_case(name)

    # Write 3 MELD files
    ontology_path = output_dir / f"{pascal}DomainOntologyMt.meld"
    vocab_path = output_dir / f"{pascal}ActionVocabMt.meld"
    rules_path = output_dir / f"{pascal}DeonticRulesMt.meld"

    _write_ontology(name, ontology, ontology_path)
    _write_action_vocab(name, ontology, vocab_path)
    _write_deontic_rules(name, ontology, results, rules_path)

    # Collect review flags
    flags = _collect_flags(results)

    # Compute statistics
    successful = [r for r in results if r.success]
    flagged = [r for r in results if r.flagged]
    obl = sum(1 for r in successful if "oughtToDo" in r.meld_expression)
    frb = sum(1 for r in successful if "forbiddenToDo" in r.meld_expression)
    prm = sum(1 for r in successful if "permittedToDo" in r.meld_expression and "forbiddenToDo" not in r.meld_expression)

    # Count unique source articles
    all_articles = {r.source_article for r in results}
    skipped_articles = {r.source_article for r in results if not r.success} - {
        r.source_article for r in results if r.success
    }

    export = DomainExport(
        domain_name=name,
        ontology_path=str(ontology_path),
        vocab_path=str(vocab_path),
        rules_path=str(rules_path),
        total_rules=len(successful),
        auto_generated=len(successful) - len([r for r in successful if r.flagged]),
        flagged_for_review=len(flagged),
        flags=tuple(flags),
        articles_processed=len(all_articles),
        articles_skipped=len(skipped_articles),
        obligations=obl,
        prohibitions=frb,
        permissions=prm,
    )

    # Write review report (with traceability: source_text per rule)
    review_path = output_dir / f"{name}-review.json"
    _write_review_report(export, results, review_path)

    logger.info("Exported domain '%s': %s", name, export.summary())
    return export


def _collect_flags(results: list[CompilationResult]) -> list[ReviewFlag]:
    """Collect review flags from compilation results."""
    flags: list[ReviewFlag] = []
    for idx, r in enumerate(results):
        if not r.flagged:
            continue
        # Parse individual flag reasons
        for part in r.flag_reason.split("; "):
            if ": " in part:
                reason, detail = part.split(": ", 1)
            else:
                reason, detail = part, ""
            flags.append(ReviewFlag(
                article_ref=r.source_article,
                rule_index=idx,
                reason=reason,
                detail=detail,
                meld_expression=r.meld_expression,
            ))
    return flags


# ── MELD file writers ───────────────────────────────────────────────


def _write_ontology(
    name: str,
    ontology: DomainOntology,
    path: Path,
) -> None:
    """Write the ontology .meld file."""
    pascal = _pascal_case(name)
    mt_name = f"{pascal}DomainOntologyMt"
    lines = [
        "(aegis-schema-version 1)",
        f"(case {mt_name})",
        "",
    ]

    # Role declarations
    if ontology.roles:
        lines.append(";; ── Agent Roles ────────────────────────────────")
        for role in ontology.roles:
            lines.append(f"(isa {role.meld_symbol} {pascal}Role)")
        lines.append(f"(genls {pascal}Role IntelligentAgent)")
        lines.append("")

    # Role hierarchy
    if ontology.role_hierarchy:
        lines.append(";; ── Role Hierarchy ─────────────────────────────")
        for child, parent in ontology.role_hierarchy:
            lines.append(f"(genls {child} {parent})")
        lines.append("")

    # Data categories
    if ontology.data_categories:
        lines.append(";; ── Data Categories ────────────────────────────")
        for cat in ontology.data_categories:
            lines.append(f"(isa {cat} DataCategory)")
        lines.append("")

    # Deontic infrastructure
    lines.extend([
        ";; ── Deontic Infrastructure ─────────────────────",
        "(genlPreds oughtToDo-WRT permittedToDo-WRT)",
        "(negationPreds oughtToDo forbiddenToDo)",
        "(negationPreds permittedToDo forbiddenToDo)",
        "(negationPreds permittedToDo-WRT forbiddenToDo-WRT)",
    ])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_action_vocab(
    name: str,
    ontology: DomainOntology,
    path: Path,
) -> None:
    """Write the ActionVocab .meld file."""
    from aegis.editor.meld_writer import write_action_vocab_meld

    actions = [
        (act.meld_symbol, act.parameters)
        for act in ontology.actions
    ]
    write_action_vocab_meld(name, actions, path)


def _write_deontic_rules(
    name: str,
    ontology: DomainOntology,
    results: list[CompilationResult],
    path: Path,
) -> None:
    """Write the deontic rules .meld file."""
    pascal = _pascal_case(name)
    mt_name = f"{pascal}DeonticRulesMt"
    lines = [
        "(aegis-schema-version 1)",
        f"(case {mt_name})",
        "",
    ]

    # Group successful results by source article
    by_article: dict[str, list[CompilationResult]] = {}
    for r in results:
        if r.success and r.meld_expression:
            by_article.setdefault(r.source_article, []).append(r)

    for article, article_results in sorted(by_article.items()):
        lines.append(f";; ── {article} ──")
        for r in article_results:
            if r.flagged:
                lines.append(f";; [FLAGGED: {r.flag_reason}]")
            lines.append(r.meld_expression)
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_review_report(
    export: DomainExport,
    results: list[CompilationResult],
    path: Path,
) -> None:
    """Write the review report as JSON with traceability."""
    # Build per-rule traceability entries
    rules_detail = []
    for r in results:
        if r.success:
            rules_detail.append({
                "source_article": r.source_article,
                "source_text": r.source_text,
                "meld_expression": r.meld_expression,
                "summary": r.natural_language_summary,
                "flagged": r.flagged,
                "flag_reason": r.flag_reason,
            })

    report = {
        "domain": export.domain_name,
        "total_rules": export.total_rules,
        "auto_generated": export.auto_generated,
        "flagged_for_review": export.flagged_for_review,
        "flagged_reasons": _count_flag_reasons(export.flags),
        "coverage": {
            "articles_processed": export.articles_processed,
            "articles_skipped": export.articles_skipped,
            "obligations": export.obligations,
            "prohibitions": export.prohibitions,
            "permissions": export.permissions,
        },
        "rules": rules_detail,
        "flags": [
            {
                "article_ref": f.article_ref,
                "rule_index": f.rule_index,
                "reason": f.reason,
                "detail": f.detail,
                "meld_expression": f.meld_expression,
            }
            for f in export.flags
        ],
    }
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _count_flag_reasons(flags: tuple[ReviewFlag, ...]) -> dict[str, int]:
    """Count flags by reason type."""
    counts: dict[str, int] = {}
    for f in flags:
        counts[f.reason] = counts.get(f.reason, 0) + 1
    return counts


def _pascal_case(s: str) -> str:
    """Convert a string to PascalCase."""
    return "".join(word.capitalize() for word in s.replace("-", "_").split("_"))
