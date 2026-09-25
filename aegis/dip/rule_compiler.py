"""Stage 5: Deterministic rule compiler.

Compiles NormativeStatements + DomainOntology into validated MELD
expressions via RuleProposal → build_meld_expression(). No LLM
dependency — purely deterministic.

Flags rules that need human review (vague terms, low confidence,
unmapped terms, delegation clauses).
"""

from __future__ import annotations

import logging
import re

from aegis.dip.models import (
    CompilationResult,
    DomainOntology,
    NormativeStatement,
)
from aegis.dip.ontology_builder import _sanitize_symbol
from aegis.editor.meld_generator import RuleProposal, build_meld_expression

logger = logging.getLogger(__name__)

_MAX_SYMBOL_WORDS = 5  # max words in a fallback action symbol

# Patterns that indicate delegation / opening clauses
_DELEGATION_PATTERNS = (
    "national law",
    "member state",
    "domestic law",
    "implementing act",
    "delegated act",
    "may provide",
    "may lay down",
    "can specify",
    "as determined by",
)


def compile_rules(
    statements: list[NormativeStatement],
    ontology: DomainOntology,
    *,
    confidence_threshold: float = 0.7,
    verify: bool = False,
) -> list[CompilationResult]:
    """Compile normative statements into validated MELD expressions.

    Args:
        statements: Extracted normative statements.
        ontology: Domain ontology with role/action mappings.
        confidence_threshold: Statements below this are flagged.
        verify: If True, run full 4-stage VerificationPipeline per rule
            (stages: syntax, symbol, conflict, functional).

    Returns:
        List of CompilationResults, deduplicated by MELD expression.
    """
    verifier = _build_verifier(ontology) if verify else None

    results: list[CompilationResult] = []
    seen_expressions: set[str] = set()

    for stmt in statements:
        result = _compile_single(stmt, ontology, confidence_threshold)
        # Deduplicate by MELD expression
        if result.success and result.meld_expression in seen_expressions:
            logger.debug("Skipping duplicate: %s", result.meld_expression[:80])
            continue
        if result.success:
            seen_expressions.add(result.meld_expression)

        # Run 4-stage verification if requested
        if verify and result.success and verifier is not None:
            result = _run_verification(result, stmt, ontology, verifier)

        results.append(result)

    # Summary
    ok = sum(1 for r in results if r.success)
    flagged = sum(1 for r in results if r.flagged)
    failed = sum(1 for r in results if not r.success)
    logger.info(
        "Compiled %d statements: %d OK (%d unique), %d flagged, %d failed",
        len(statements), ok, len(seen_expressions), flagged, failed,
    )
    return results


def _compile_single(
    stmt: NormativeStatement,
    ontology: DomainOntology,
    confidence_threshold: float,
) -> CompilationResult:
    """Compile a single statement into a CompilationResult."""
    flags: list[tuple[str, str]] = []  # (reason, detail)

    # Map subject → agent_role
    agent_role = _map_subject(stmt.subject, ontology)
    if not agent_role:
        flags.append(("unmapped_term", f"subject: {stmt.subject}"))
        agent_role = "*"  # fallback to wildcard

    # Map action → action_type
    action_type = _map_action(stmt.action, ontology)
    if not action_type:
        flags.append(("unmapped_term", f"action: {stmt.action}"))
        action_type = _fallback_action_symbol(stmt.action)

    # Build proposition parameters from conditions
    prop_params = _build_proposition_params(stmt, ontology)

    # Determine defeasibility
    defeasible = True  # default

    # Determine code of conduct
    code = ontology.codes[0] if ontology.codes else ""

    # Check for flags
    if stmt.vague_terms:
        for term in stmt.vague_terms:
            flags.append(("vague_term", term))

    if stmt.confidence < confidence_threshold:
        flags.append(("low_confidence", f"{stmt.confidence:.2f}"))

    if _is_delegation_clause(stmt):
        flags.append(("delegation_clause", stmt.original_text or stmt.action))

    # Build RuleProposal
    proposal = RuleProposal(
        modality=_normalize_modality(stmt.modality),
        agent_role=agent_role,
        code_of_conduct=code,
        action_type=action_type,
        proposition_parameters=prop_params,
        defeasible=defeasible,
        reasoning=f"Source: {stmt.source_article}",
        natural_language_summary=f"[{stmt.modality}] {stmt.subject}: {stmt.action}",
    )

    nl_summary = f"[{stmt.modality}] {stmt.subject}: {stmt.action}"

    try:
        meld_expr = build_meld_expression(proposal)
    except Exception as e:
        return CompilationResult(
            source_article=stmt.source_article,
            success=False,
            error=f"build_meld_expression failed: {e}",
            flagged=bool(flags),
            flag_reason="; ".join(f"{r}: {d}" for r, d in flags),
            source_text=stmt.original_text,
            natural_language_summary=nl_summary,
        )

    # Validate via parse_meld + extract_norm
    validation_error = _validate_meld(meld_expr)
    if validation_error:
        return CompilationResult(
            source_article=stmt.source_article,
            success=False,
            meld_expression=meld_expr,
            error=validation_error,
            flagged=bool(flags),
            flag_reason="; ".join(f"{r}: {d}" for r, d in flags),
            source_text=stmt.original_text,
            natural_language_summary=nl_summary,
        )

    return CompilationResult(
        source_article=stmt.source_article,
        success=True,
        meld_expression=meld_expr,
        flagged=bool(flags),
        flag_reason="; ".join(f"{r}: {d}" for r, d in flags),
        source_text=stmt.original_text,
        natural_language_summary=nl_summary,
    )


# ── Mapping helpers ─────────────────────────────────────────────────


def _extract_variants(text: str) -> list[str]:
    """Extract matching variants from a text.

    Handles:
    - Parenthesized hints: "custodian (controller)" →
      ["custodian (controller)", "custodian", "controller"]
    - Slash-separated: "controller / data controller" →
      ["controller / data controller", "controller", "data controller"]
    - Conjunctions: "controller and processor" →
      [..., "controller", "processor"]
    """
    variants = [text]

    # Extract parenthesized content
    m = re.search(r"\(([^)]+)\)", text)
    if m:
        inside = m.group(1).strip()
        outside = re.sub(r"\s*\([^)]+\)\s*", " ", text).strip()
        variants.append(outside)
        variants.append(inside)

    # Split on " / " (alternative natural_names from ontology)
    if " / " in text:
        for part in text.split(" / "):
            part = part.strip()
            if part and part not in variants:
                variants.append(part)

    # Split on the English conjunction
    for conj in (" and ",):
        if conj in text.lower():
            parts = re.split(conj, text, flags=re.IGNORECASE)
            for part in parts:
                part = part.strip()
                if part and part not in variants:
                    variants.append(part)

    return variants


def _map_subject(subject: str, ontology: DomainOntology) -> str:
    """Map a natural language subject to a MELD role symbol.

    Tries exact match, then case-insensitive, then substring match.
    Also extracts parenthesized hints: "custodian (controller)"
    tries "custodian", "controller" separately.
    """
    if not subject:
        return ""

    variants = _extract_variants(subject)

    for variant in variants:
        # Exact match
        if variant in ontology.role_map:
            return ontology.role_map[variant]

        # Case-insensitive match
        variant_lower = variant.lower()
        for natural, symbol in ontology.role_map.items():
            if natural.lower() == variant_lower:
                return symbol

        # Substring match (e.g. "the data controller" → "data controller")
        for natural, symbol in ontology.role_map.items():
            if natural.lower() in variant_lower or variant_lower in natural.lower():
                return symbol

        # Try matching against role symbols directly (camelCase)
        for role in ontology.roles:
            if role.meld_symbol.lower() == variant_lower:
                return role.meld_symbol
            # Also try: "controller" matches "dataController"
            if variant_lower in role.meld_symbol.lower():
                return role.meld_symbol

        # Try matching role descriptions
        for role in ontology.roles:
            if role.description and variant_lower in role.description.lower():
                return role.meld_symbol

    return ""


def _map_action(action: str, ontology: DomainOntology) -> str:
    """Map a natural language action to a MELD action symbol.

    Tries exact match, then case-insensitive, then substring match.
    Also handles parenthesized hints and keyword extraction.
    """
    if not action:
        return ""

    variants = _extract_variants(action)

    for variant in variants:
        # Exact match
        if variant in ontology.action_map:
            return ontology.action_map[variant]

        # Case-insensitive match
        variant_lower = variant.lower()
        for natural, symbol in ontology.action_map.items():
            if natural.lower() == variant_lower:
                return symbol

        # Substring match
        for natural, symbol in ontology.action_map.items():
            if natural.lower() in variant_lower or variant_lower in natural.lower():
                return symbol

        # Try matching against action symbols directly
        for act in ontology.actions:
            if act.meld_symbol.lower() == variant_lower:
                return act.meld_symbol
            if variant_lower in act.meld_symbol.lower():
                return act.meld_symbol

    # Keyword extraction: try matching individual significant words
    keywords = _extract_keywords(action)
    for kw in keywords:
        for act in ontology.actions:
            if kw in act.meld_symbol.lower() or kw in act.natural_name.lower():
                return act.meld_symbol

    return ""


def _extract_keywords(text: str) -> list[str]:
    """Extract significant keywords from action text for fuzzy matching.

    Filters out common stop words and returns lowercase keywords
    sorted by length (longer = more specific = tried first).
    """
    stop_words = {
        "the", "a", "an", "of", "to", "in", "for", "with", "by", "from",
        "on", "at", "is", "are", "was", "were", "be", "been", "being",
        "has", "have", "had", "do", "does", "did", "shall", "must", "may",
        "can", "will", "would", "should", "could", "not", "no", "and", "or",
        "that", "this", "which", "who", "whom", "when", "where", "how",
    }
    words = re.findall(r"[a-zA-Z]+", text.lower())
    keywords = [w for w in words if w not in stop_words and len(w) > 3]
    return sorted(keywords, key=len, reverse=True)


def _fallback_action_symbol(action: str) -> str:
    """Generate a fallback action symbol from natural language.

    Sanitizes to ASCII camelCase, truncates to max words.
    """
    # Extract keywords instead of using full sentence
    keywords = _extract_keywords(action)
    if not keywords:
        return "unknownAction"

    # Take first N significant keywords
    selected = keywords[:_MAX_SYMBOL_WORDS]

    # Build camelCase from keywords
    symbol = _sanitize_symbol(" ".join(selected))
    if not symbol:
        return "unknownAction"

    return symbol


def _build_proposition_params(
    stmt: NormativeStatement,
    ontology: DomainOntology,
) -> dict[str, str]:
    """Build proposition parameters from conditions and object description."""
    params: dict[str, str] = {}

    # Map data categories from conditions/object_description
    all_text = f"{stmt.object_description} {' '.join(stmt.conditions)}"
    for cat in ontology.data_categories:
        if cat.lower() in all_text.lower():
            params["dataCategory"] = cat
            break

    return params


def _normalize_modality(modality: str) -> str:
    """Normalize modality string to MELD-compatible form."""
    m = modality.upper().strip()
    if m in ("OBLIGATORY", "FORBIDDEN", "PERMITTED"):
        return m
    if m in ("OBLIGATION", "MANDATORY", "REQUIRED"):
        return "OBLIGATORY"
    if m in ("PROHIBITION", "PROHIBITED"):
        return "FORBIDDEN"
    if m in ("PERMISSION", "ALLOWED"):
        return "PERMITTED"
    return "FORBIDDEN"  # fail-closed default


def _is_delegation_clause(stmt: NormativeStatement) -> bool:
    """Check if a statement is a delegation/opening clause."""
    check_text = f"{stmt.action} {stmt.object_description} {stmt.original_text}".lower()
    return any(pattern in check_text for pattern in _DELEGATION_PATTERNS)


def _validate_meld(meld_expr: str) -> str:
    """Validate a MELD expression via parse_meld + extract_norm.

    Returns empty string on success, error message on failure.
    """
    try:
        from aegis.kb.meld_loader import extract_norm, parse_meld

        assertions = parse_meld(meld_expr)
        if not assertions:
            return "parse_meld returned no assertions"
        # extract_norm may return None for non-deontic assertions
        norm = extract_norm(assertions[0], "<dip>", "<dip>")
        if norm is None:
            return "extract_norm returned None — not a valid deontic assertion"
        return ""
    except Exception as e:
        return f"Validation error: {e}"


# ── 4-stage verification integration ───────────────────────────────


def _build_verifier(ontology: DomainOntology) -> object | None:
    """Build a VerificationPipeline from a DIP ontology.

    Returns None if the editor module is not available.
    """
    try:
        from aegis.editor.domain_model import CodeOfConductInfo, DomainInfo, Role
        from aegis.editor.verification import VerificationPipeline

        roles = [
            Role(id=r.meld_symbol, name=r.meld_symbol)
            for r in ontology.roles
        ]
        codes = [
            CodeOfConductInfo(id=c, name=c)
            for c in ontology.codes
        ]
        domain = DomainInfo(
            id="dip-verify",
            name="dip-verify",
            roles=roles,
            codes=codes,
            rules=[],
        )
        return VerificationPipeline(domain)
    except Exception:
        logger.warning("Could not build VerificationPipeline", exc_info=True)
        return None


def _run_verification(
    result: CompilationResult,
    stmt: NormativeStatement,
    ontology: DomainOntology,
    verifier: object,
) -> CompilationResult:
    """Run 4-stage verification on a compiled rule.

    If verification fails, flags the result but does NOT mark it as
    unsuccessful — the rule is syntactically valid, just unverified.
    """
    try:
        from aegis.editor.verification import VerificationPipeline

        assert isinstance(verifier, VerificationPipeline)

        # Build a minimal RuleProposal for the verifier
        proposal = RuleProposal(
            modality=stmt.modality,
            agent_role=result.meld_expression.split()[2] if len(result.meld_expression.split()) > 2 else "*",
            code_of_conduct=ontology.codes[0] if ontology.codes else "",
            action_type=_extract_action_from_meld(result.meld_expression),
            proposition_parameters={},
            defeasible=True,
            reasoning=f"Source: {stmt.source_article}",
            natural_language_summary=f"[{stmt.modality}] {stmt.subject}: {stmt.action}",
            meld_expression=result.meld_expression,
        )

        vr = verifier.verify(proposal)

        if not vr.passed:
            failed_stages = [
                s for s in vr.stages if s.status.value == "FAIL"
            ]
            stage_info = "; ".join(
                f"stage_{s.stage}: {s.message}" for s in failed_stages
            )
            # Append verification failure to existing flags
            flag_reason = result.flag_reason
            if flag_reason:
                flag_reason += "; "
            flag_reason += f"verification_failed: {stage_info}"

            return CompilationResult(
                source_article=result.source_article,
                success=result.success,
                meld_expression=result.meld_expression,
                error=result.error,
                flagged=True,
                flag_reason=flag_reason,
            )

        return result

    except Exception:
        logger.debug("Verification error (non-fatal)", exc_info=True)
        return result


def _extract_action_from_meld(meld_expr: str) -> str:
    """Extract the action type from a MELD expression.

    E.g. "(oughtToDo-WRT Code agent (deleteData foo))" → "deleteData"
    """
    # Find the inner proposition parentheses
    import re
    m = re.search(r"\((\w+)(?:\s|[)])", meld_expr[meld_expr.find("(", 1):])
    if m:
        return m.group(1)
    return ""
