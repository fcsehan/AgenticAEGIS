"""Stage 4: LLM-based domain ontology derivation.

Derives a coherent domain ontology (roles, actions, object categories,
hierarchies) from all extracted normative statements. Uses a single
LLM call with all statements as context.

Domain-agnostic: the ``domain_context`` parameter provides domain hints
to the LLM at runtime.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from aegis.dip.models import (
    DomainOntology,
    NormativeStatement,
    OntologyAction,
    OntologyRole,
)
from aegis.dip.prompts import (
    DEFINE_ONTOLOGY_TOOL,
    build_ontology_system_prompt,
    build_ontology_user_message,
)
from aegis.editor.llm_provider import LLMClient

logger = logging.getLogger(__name__)


def build_ontology(
    statements: list[NormativeStatement],
    client: LLMClient,
    *,
    domain_context: str = "",
) -> DomainOntology:
    """Derive a domain ontology from extracted normative statements.

    Args:
        statements: All extracted normative statements.
        client: LLM client for the API call.
        domain_context: Domain-specific hints for the LLM.

    Returns:
        Complete DomainOntology with roles, actions, categories, hierarchies.

    Raises:
        RuntimeError: If the LLM does not produce a valid ontology.
    """
    if not statements:
        logger.warning("No statements provided — returning empty ontology")
        return DomainOntology()

    system_prompt = build_ontology_system_prompt(domain_context=domain_context)

    stmt_dicts = [
        {
            "source_article": s.source_article,
            "modality": s.modality,
            "subject": s.subject,
            "action": s.action,
        }
        for s in statements
    ]

    user_message = build_ontology_user_message(stmt_dicts)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    response = client.chat(messages, tools=[DEFINE_ONTOLOGY_TOOL])
    return _parse_ontology_response(response)


def _parse_ontology_response(
    response: dict[str, Any],
) -> DomainOntology:
    """Parse LLM response into a DomainOntology.

    Raises RuntimeError if no valid define_ontology call is found.
    """
    message = response.get("choices", [{}])[0].get("message", {})
    tool_calls = message.get("tool_calls", [])

    for tc in tool_calls:
        fn = tc.get("function", {})
        if fn.get("name") != "define_ontology":
            continue

        raw_args = fn.get("arguments", "{}")
        args: dict[str, Any] = (
            json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        )
        return _args_to_ontology(args)

    raise RuntimeError(
        "LLM did not produce a define_ontology tool call. "
        f"Response: {message.get('content', '')[:200]}"
    )


def _args_to_ontology(args: dict[str, Any]) -> DomainOntology:
    """Convert tool call arguments to a DomainOntology."""
    # Parse roles
    roles: list[OntologyRole] = []
    role_map: dict[str, str] = {}
    for r in args.get("roles", []):
        natural = r.get("natural_name", "")
        symbol = _sanitize_symbol(r.get("meld_symbol", ""))
        if natural and symbol:
            roles.append(OntologyRole(
                natural_name=natural,
                meld_symbol=symbol,
                description=r.get("description", ""),
            ))
            role_map[natural] = symbol

    # Parse actions
    actions: list[OntologyAction] = []
    action_map: dict[str, str] = {}
    for a in args.get("actions", []):
        natural = a.get("natural_name", "")
        symbol = _sanitize_symbol(a.get("meld_symbol", ""))
        if natural and symbol:
            params = tuple(
                _sanitize_symbol(p) for p in a.get("parameters", [])
            )
            actions.append(OntologyAction(
                natural_name=natural,
                meld_symbol=symbol,
                parameters=params,
                description=a.get("description", ""),
            ))
            action_map[natural] = symbol

    # Parse object categories
    categories = tuple(
        _sanitize_symbol(c)
        for c in args.get("object_categories", [])
        if c
    )

    # Parse role hierarchy
    hierarchy: list[tuple[str, str]] = []
    for h in args.get("role_hierarchy", []):
        child = _sanitize_symbol(h.get("child", ""))
        parent = _sanitize_symbol(h.get("parent", ""))
        if child and parent:
            hierarchy.append((child, parent))

    # Parse codes — PascalCase (not camelCase), consistent with existing domains
    codes = tuple(
        _sanitize_pascal(c) for c in args.get("codes", []) if c
    )
    if not codes:
        codes = ("DefaultCode",)

    return DomainOntology(
        roles=tuple(roles),
        actions=tuple(actions),
        data_categories=categories,
        role_hierarchy=tuple(hierarchy),
        codes=codes,
        role_map=role_map,
        action_map=action_map,
    )


# ── Symbol sanitization ─────────────────────────────────────────────

import unicodedata

# Special cases not handled by NFKD decomposition
_SPECIAL_MAP = {"\u00df": "ss", "\u00f8": "o", "\u00d8": "O", "\u0111": "d", "\u0110": "D", "\u0142": "l", "\u0141": "L"}


def _to_ascii(s: str) -> str:
    """Transliterate any Unicode string to ASCII.

    Uses NFKD normalization (language-agnostic): decomposes accented
    characters into base + combining mark, then strips combining marks.
    Handles Latin characters with diacritics and explicit special mappings.
    Non-Latin scripts (CJK, Cyrillic, Arabic) are removed.
    """
    # Apply special cases first
    for char, replacement in _SPECIAL_MAP.items():
        s = s.replace(char, replacement)
    # NFKD decomposes diacritics into base characters and combining marks.
    normalized = unicodedata.normalize("NFKD", s)
    # Strip combining marks (category "M")
    ascii_chars = [c for c in normalized if unicodedata.category(c)[0] != "M"]
    # Encode to ASCII, drop anything that didn't survive
    return "".join(ascii_chars).encode("ascii", errors="ignore").decode()


def _sanitize_pascal(s: str) -> str:
    """Sanitize a string to PascalCase ASCII (for Codes of Conduct).

    Codes of Conduct use PascalCase in MELD, unlike roles/actions which
    use camelCase. E.g. "DataProtection", "EngagementRules".
    """
    camel = _sanitize_symbol(s)
    if not camel:
        return ""
    return camel[0].upper() + camel[1:]


def _sanitize_symbol(s: str) -> str:
    """Sanitize a string to a valid MELD camelCase ASCII symbol.

    Language-agnostic: uses Unicode NFKD normalization for all scripts.
    - Transliterates accented/diacritic chars to ASCII base letters
    - Removes non-alphanumeric chars (except spaces for word splitting)
    - Converts to camelCase (first char lowercase)
    """
    if not s:
        return ""

    # Transliterate to ASCII (language-agnostic)
    s = _to_ascii(s)

    # Remove non-alphanumeric except spaces and underscores
    s = re.sub(r"[^a-zA-Z0-9_ ]", "", s)

    # Convert to camelCase
    words = s.split()
    if not words:
        return ""
    if len(words) == 1:
        w = words[0]
        # Preserve existing camelCase
        if any(c.isupper() for c in w[1:]):
            return w[0].lower() + w[1:]
        return w[0].lower() + w[1:]

    result = words[0][0].lower() + words[0][1:]
    for w in words[1:]:
        if w:
            result += w[0].upper() + w[1:]
    return result
