"""LLM prompts and tool schemas for DIP stages 3 and 4.

All prompts are domain-parameterized: the ``domain_context`` argument
provides domain-specific hints at runtime. The prompts themselves
contain no hardcoded domain knowledge.

Tool schemas follow the OpenAI function-calling format, consistent
with ``aegis.editor.meld_generator.PROPOSE_RULE_TOOL``.
"""

from __future__ import annotations

from typing import Any


# ── Stage 3: Extractor Tool + Prompt ────────────────────────────────

EXTRACT_STATEMENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "extract_normative_statement",
        "description": (
            "Extract a single normative statement from the given text. "
            "Call this tool once per distinct obligation, prohibition, or "
            "permission found in the chunk. A single chunk may contain "
            "multiple statements."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source_ref": {
                    "type": "string",
                    "description": (
                        "The precise source reference, e.g. 'Art. 17(1)' or "
                        "'Section 5.2'. Must match the article_ref provided."
                    ),
                },
                "modality": {
                    "type": "string",
                    "enum": ["OBLIGATORY", "FORBIDDEN", "PERMITTED"],
                    "description": (
                        "The deontic modality. OBLIGATORY = must/shall, "
                        "FORBIDDEN = must not/shall not/prohibited, "
                        "PERMITTED = may/is allowed/has the right."
                    ),
                },
                "subject": {
                    "type": "string",
                    "description": (
                        "Who is bound by this norm, in natural language. "
                        "E.g. 'data controller', 'employee', 'commander'."
                    ),
                },
                "action": {
                    "type": "string",
                    "description": (
                        "What action is regulated, in natural language. "
                        "E.g. 'deletion of personal data', 'transfer of classified info'."
                    ),
                },
                "object_description": {
                    "type": "string",
                    "description": (
                        "Additional context about the object or circumstances. "
                        "E.g. 'upon request of the data subject'."
                    ),
                },
                "conditions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Triggering conditions for this norm. "
                        "E.g. ['purpose no longer necessary', 'consent withdrawn']."
                    ),
                },
                "exceptions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "References to exception clauses. "
                        "E.g. ['Art. 17(3)', 'Section 7.1']."
                    ),
                },
                "vague_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Vague or indeterminate terms that need operationalization. "
                        "E.g. ['without undue delay', 'appropriate measures', "
                        "'reasonable effort']."
                    ),
                },
                "confidence": {
                    "type": "number",
                    "description": (
                        "Your confidence in this extraction (0.0 to 1.0). "
                        "Lower confidence for ambiguous text or complex "
                        "conditional structures."
                    ),
                },
            },
            "required": ["source_ref", "modality", "subject", "action", "confidence"],
        },
    },
}


def build_extractor_system_prompt(*, domain_context: str = "") -> str:
    """Build the system prompt for the normative statement extractor.

    Args:
        domain_context: Optional domain-specific hints for the LLM.
            E.g. "Data protection law (GDPR). Key roles: data controller,
            data subject, supervisory authority."
    """
    context_block = ""
    if domain_context:
        context_block = f"""
## Domain Context
{domain_context}
"""

    return f"""\
You are a normative text analyst. Your task is to extract structured \
normative statements from text chunks of any normative document \
(laws, regulations, standards, corporate policies, military rules, \
medical guidelines, etc.).

For each chunk, identify every distinct obligation, prohibition, or \
permission and call the extract_normative_statement tool once per statement.

## Deontic Modalities
- **OBLIGATORY**: The subject MUST / SHALL / IS REQUIRED TO perform the action.
- **FORBIDDEN**: The subject MUST NOT / SHALL NOT / IS PROHIBITED FROM the action.
- **PERMITTED**: The subject MAY / IS ALLOWED TO / HAS THE RIGHT TO the action.

## CRITICAL: Subject and Action Format

**subject** must be a PERSON or ORGANIZATION who acts — never a data object or process:
- GOOD: "data controller", "controller", "commander", "employee", "organization"
- BAD: "personal data" ← this is a data object, not an actor
- BAD: "data processing" ← this is a process, not an actor
- BAD: "the controller under Art. 4" ← no articles, no references
- BAD: "controller and processor" ← split into separate statements

For PASSIVE constructions ("Data must be processed lawfully"), identify the \
IMPLIED actor. In regulations, this is typically the "controller" / "data controller" \
or "organization". Never use data objects as subjects.

If a norm applies to MULTIPLE actors ("controller and processor"), \
create SEPARATE statements for each actor.

**action** must be a SHORT VERB + OBJECT — 2 to 5 words maximum:
- GOOD: "erase data", "delete personal data", "grant access", "report incident"
- BAD: "be" ← too vague, must include the object
- BAD: "occur" ← too vague
- BAD: "erase personal data without undue delay if a ground applies" ← too long, move conditions to the conditions field

Use English source documents and write all subjects, actions and explanations in English.

## Instructions
1. Extract EVERY normative statement — do not skip any.
2. Use the exact article/section reference provided in the chunk metadata.
3. Keep subject SHORT (1-3 words, canonical role name from the text).
4. Keep action SHORT (2-5 words, verb + direct object).
5. Put qualifiers, conditions, recipients into the conditions and object_description fields.
6. List references to exception clauses (e.g. "Art. 17(3)", "Section 7.1").
7. Flag vague terms (e.g. "adequate", "reasonable", "without undue delay", "appropriate").
8. Set confidence lower for ambiguous or complex text.
9. One chunk may contain multiple statements — extract them all.
{context_block}
## Examples

**Legal text (OBLIGATORY):**
"The controller must erase personal data without undue delay."
→ subject: "controller", action: "erase data", \
vague_terms: ["without undue delay"]

**English policy (FORBIDDEN):**
"Employees must not transfer confidential data to external systems."
→ subject: "employee", action: "transfer confidential data", \
conditions: ["to external systems"]

**English standard (OBLIGATORY):**
"The organization shall implement access control measures."
→ subject: "organization", action: "implement access control"

**Military (FORBIDDEN):**
"Commanders are prohibited from engaging civilian targets."
→ subject: "commander", action: "engage civilian targets"

**Medical (OBLIGATORY):**
"The investigator must report adverse events within 24 hours."
→ subject: "clinical investigator", action: "report events", \
conditions: ["within 24 hours"], vague_terms: []"""


def build_extractor_user_message(
    chunks: list[dict[str, str]],
) -> str:
    """Build the user message for a batch of chunks.

    Args:
        chunks: List of dicts with keys "article_ref", "text", "chunk_type".
    """
    parts: list[str] = []
    parts.append(
        f"Extract all normative statements from the following {len(chunks)} "
        f"text chunks. Call extract_normative_statement once per statement.\n"
    )
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"--- Chunk {i} ---\n"
            f"Reference: {chunk['article_ref']}\n"
            f"Type: {chunk['chunk_type']}\n"
            f"Text: {chunk['text']}\n"
        )
    return "\n".join(parts)


# ── Stage 4: Ontology Builder Tool + Prompt ─────────────────────────

DEFINE_ONTOLOGY_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "define_ontology",
        "description": (
            "Define the complete domain ontology derived from all extracted "
            "normative statements. Call this tool exactly once with the full "
            "ontology."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "roles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "natural_name": {
                                "type": "string",
                                "description": "Role name in natural language.",
                            },
                            "meld_symbol": {
                                "type": "string",
                                "description": (
                                    "MELD symbol in camelCase ASCII. "
                                    "E.g. 'dataController', 'commander'."
                                ),
                            },
                            "description": {
                                "type": "string",
                                "description": "Brief role description.",
                            },
                        },
                        "required": ["natural_name", "meld_symbol"],
                    },
                    "description": "All domain roles.",
                },
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "natural_name": {
                                "type": "string",
                                "description": "Action name in natural language.",
                            },
                            "meld_symbol": {
                                "type": "string",
                                "description": (
                                    "MELD symbol in camelCase ASCII. "
                                    "E.g. 'deleteData', 'shareIntelligence'."
                                ),
                            },
                            "parameters": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Parameter names for this action. "
                                    "E.g. ['dataCategory', 'recipient']."
                                ),
                            },
                            "description": {
                                "type": "string",
                                "description": "Brief action description.",
                            },
                        },
                        "required": ["natural_name", "meld_symbol"],
                    },
                    "description": "All domain action types.",
                },
                "object_categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Domain object categories as MELD symbols. "
                        "E.g. ['personalData', 'confidentialInfo', 'classifiedDoc']."
                    ),
                },
                "role_hierarchy": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "child": {"type": "string"},
                            "parent": {"type": "string"},
                        },
                        "required": ["child", "parent"],
                    },
                    "description": (
                        "Role hierarchy pairs (child genls parent). "
                        "E.g. [{'child': 'dpo', 'parent': 'dataController'}]."
                    ),
                },
                "codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Codes of conduct for WRT rules. "
                        "E.g. ['DataProtection', 'InformationSecurity']."
                    ),
                },
            },
            "required": ["roles", "actions", "codes"],
        },
    },
}


def build_ontology_system_prompt(*, domain_context: str = "") -> str:
    """Build the system prompt for the ontology builder.

    Args:
        domain_context: Optional domain-specific hints.
    """
    context_block = ""
    if domain_context:
        context_block = f"""
## Domain Context
{domain_context}
"""

    return f"""\
You are a domain ontology architect for the AEGIS normative engine. \
Your task is to derive a complete, consistent domain ontology from \
a set of extracted normative statements. The statements may come from \
any domain: law, military, medical, corporate, IT security, finance, etc.

## MELD Symbol Conventions
- **camelCase** for all symbols (e.g. dataController, deleteData)
- **ASCII only** — no umlauts, accents, or special characters
  - Normalize diacritics to ASCII equivalents.
- **No spaces** — compound terms are camelCased
- Role symbols: noun-based (e.g. dataController, commander, investigator)
- Action symbols: verb + object (e.g. deleteData, grantAccess, reportIncident)

## CRITICAL: natural_name Format

The `natural_name` field is used to map extracted statements back to ontology \
symbols. It MUST contain ALL variant terms that appear in the statements, \
separated by " / ". This ensures that string matching succeeds regardless of \
which variant the extractor used.

Format: "source_term / canonical_equivalent"

Examples for different domains:
- Data protection: natural_name: "controller / data controller"
- Alternate wording: natural_name: "party controlling data / data controller"
- Military: natural_name: "commanding officer / commander"
- Medical: natural_name: "clinical investigator / investigator"
- Single canonical term: natural_name: "employee" (no variant needed)

If the statements contain MULTIPLE variants of the same role (e.g. \
"controller", "the controller", "data controller"), list ALL of them:
  natural_name: "controller / the controller / data controller"

Every subject that appears in the statements below MUST appear verbatim \
in at least one natural_name. If a subject cannot be matched, the entire \
pipeline fails for that rule.

## Instructions
1. Identify ALL distinct roles from the statement subjects. Group synonyms.
2. Identify ALL distinct action types from the statement actions. Group synonyms.
3. Identify object categories (data types, document types, resource types).
4. Define role hierarchies where a more specific role inherits from a general one.
5. Propose at least one Code of Conduct name for grouping the norms.
6. Ensure COMPLETENESS: every subject and action in the statements MUST map \
to exactly one role or action in the ontology.
{context_block}
## Domain Examples (for reference only — adapt to the actual domain)

**Data Protection:**
- Roles: "controller / data controller" → dataController
- Actions: "erase data / delete data" → deleteData

**Military:**
- Roles: "commanding officer / commander" → commander
- Actions: "engage a target / engage target" → engageTarget

**Medical:**
- Roles: "clinical investigator / investigator" → investigator
- Actions: "report an incident / report event" → reportEvent

**Corporate:**
- Roles: "staff member / employee" → employee
- Actions: "classify information / classify data" → classifyData"""


def build_ontology_user_message(
    statements: list[dict[str, str]],
) -> str:
    """Build the user message with all extracted statements.

    Args:
        statements: List of dicts with keys like "source_article",
            "modality", "subject", "action", etc.
    """
    parts: list[str] = []
    parts.append(
        f"Derive the complete domain ontology from these {len(statements)} "
        f"normative statements. Call define_ontology exactly once.\n"
    )
    for i, stmt in enumerate(statements, 1):
        parts.append(
            f"{i}. [{stmt.get('modality', '?')}] "
            f"Subject: {stmt.get('subject', '?')} | "
            f"Action: {stmt.get('action', '?')} | "
            f"Source: {stmt.get('source_article', '?')}"
        )
    return "\n".join(parts)
