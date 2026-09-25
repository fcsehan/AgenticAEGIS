"""AEGIS-1005: System Prompts & Domain-Prompt-Templates.

Defines PromptTemplate — a domain-specific system prompt for LLM agents.
Templates can be loaded from files or constructed programmatically.

The system prompt configures the LLM as a domain-specific agent that uses
the Guard as the ONLY way to execute actions (I5 enforcement).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from aegis.guard.registry import ActionTypeRegistry


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """A domain-specific system prompt template.

    Attributes:
        domain: Domain identifier (e.g. "ia_mission").
        role_description: What the agent is and what it does.
        available_actions: Action types the agent can propose.
        guard_instructions: How the agent handles FORBIDDEN/UNDECIDABLE.
        template: The full template string with {placeholders}.
        available_actions_detailed: Pre-rendered multi-line block of
            actions with disambiguation hints (description, synonyms,
            not-to-be-confused-with). Populated by
            ``with_disambiguation_hints`` (AEGIS-2904, Epic 29). Empty
            by default; templates that include the
            ``{available_actions_detailed}`` placeholder will fall back
            to the flat ``{available_actions}`` listing if this field
            is empty.
    """

    domain: str
    role_description: str
    available_actions: list[str] = field(default_factory=list)
    guard_instructions: str = ""
    template: str = ""
    available_actions_detailed: str = ""

    def render(self, context: dict[str, str] | None = None) -> str:
        """Render the full system prompt.

        If a template is set, uses str.format_map with context.
        Otherwise, assembles from component fields.

        Args:
            context: Optional substitution values for template placeholders.
        """
        if self.template:
            detailed = self.available_actions_detailed or ", ".join(self.available_actions)
            values: dict[str, str] = {
                "domain": self.domain,
                "role_description": self.role_description,
                "available_actions": ", ".join(self.available_actions),
                "available_actions_detailed": detailed,
                "guard_instructions": self.guard_instructions,
            }
            if context:
                values.update(context)
            return self.template.format_map(_SafeFormatMap(values))

        return self._assemble()

    def _assemble(self) -> str:
        """Assemble system prompt from component fields."""
        sections = [self.role_description]

        if self.available_actions:
            actions_str = ", ".join(self.available_actions)
            sections.append(f"Available actions: {actions_str}")

        sections.append(
            "You MUST call the aegis_check tool before performing any action. "
            "You cannot act without guard approval."
        )

        if self.guard_instructions:
            sections.append(self.guard_instructions)
        else:
            sections.append(_DEFAULT_GUARD_INSTRUCTIONS)

        return "\n\n".join(sections)

    def with_registry(self, registry: ActionTypeRegistry) -> PromptTemplate:
        """Return a copy with ``available_actions`` replaced from *registry*.

        Keeps hardcoded lists as fallback when no actions in registry.
        """
        actions = registry.action_types
        if not actions:
            return self
        return replace(self, available_actions=actions)

    def with_disambiguation_hints(
        self,
        registry: ActionTypeRegistry,
    ) -> PromptTemplate:
        """Return a copy whose ``available_actions_detailed`` field is
        populated from MELD-declared disambiguation metadata.

        For each action in ``available_actions`` (or in the registry if
        the field is empty), the rendered block contains:

        - the action name
        - the ``actionDescription`` line, when present
        - a ``Synonyms:`` line listing all ``actionSynonym`` phrases
        - a ``Do not confuse with:`` line listing every action declared
          in ``notToBeConfusedWith``

        Actions without any disambiguation metadata are listed plainly,
        so partially-annotated domains still render cleanly.

        Per AEGIS-2904: this is the LLM-side hook for the
        Action-Substitution mitigation suite. The Guard does not consume
        the rendered block — it is purely a heuristic shown to the LLM
        before it picks an action.
        """
        names = self.available_actions or registry.action_types
        if not names:
            return self
        block = format_disambiguation_hints(registry, names)
        return replace(self, available_actions_detailed=block)

    @classmethod
    def from_file(cls, path: Path, domain: str) -> PromptTemplate:
        """Load a prompt template from a text file.

        The file should contain the full template text with optional
        {placeholders} for context substitution.
        """
        template_text = path.read_text(encoding="utf-8").strip()
        return cls(
            domain=domain,
            role_description="",
            template=template_text,
        )


def format_disambiguation_hints(
    registry: ActionTypeRegistry,
    action_types: list[str],
) -> str:
    """Render a multi-line action listing with disambiguation hints.

    Output is intended to be embedded into an LLM system prompt. Each
    action gets:

    - ``- <name>``
    - ``  <description>`` if ``actionDescription`` is set
    - ``  Synonyms: "x", "y"`` if ``actionSynonym`` entries exist
    - ``  Do not confuse with: a, b`` if ``notToBeConfusedWith`` is set

    No trailing newline. Order follows the input list. Empty registry
    returns an empty string.

    AEGIS-2904 (Epic 29): pure rendering, no policy. Called from
    ``PromptTemplate.with_disambiguation_hints``.
    """
    if not action_types:
        return ""
    lines: list[str] = []
    for name in action_types:
        lines.append(f"- {name}")
        description = registry.get_description(name)
        if description:
            lines.append(f"  {description}")
        synonyms = registry.get_synonyms(name)
        if synonyms:
            quoted = ", ".join(f'"{s}"' for s in synonyms)
            lines.append(f"  Synonyms: {quoted}")
        confusables = registry.get_confusables(name)
        if confusables:
            others = ", ".join(pair.other for pair in confusables)
            lines.append(f"  Do not confuse with: {others}")
    return "\n".join(lines)


class _SafeFormatMap(dict[str, str]):
    """Dict subclass that returns '{key}' for missing keys instead of raising."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


_DEFAULT_GUARD_INSTRUCTIONS = """\
When the guard returns FORBIDDEN:
- Do NOT attempt to circumvent the prohibition
- Explain the prohibition to the user
- Suggest an alternative action if possible
- Call aegis_check with the alternative

When the guard returns UNDECIDABLE:
- Inform the user that the action requires human authorization
- Do NOT proceed without explicit approval"""


CANDIDATE_LIST_INSTRUCTIONS = """\
When the user's intent could plausibly map to several action types, do
not pick one. List **all** plausibly applicable candidates and call
``aegis_check_candidates`` with the full list. The Guard will pick the
narrowest PERMITTED action under the declared ``narrowerThan`` partial
order; this protects against silent privilege escalation when a broader
action would also have been permitted (Action-Substitution mitigation,
Epic 32).

Examples:

- User intent "view diagnosis" with available actions
  ``readDiagnosis`` and ``readPatientRecord``: pass *both*; the Guard
  returns ``readDiagnosis`` because it is narrower.
- User intent unambiguous: pass a single-element list. The result is
  identical to ``aegis_check`` modulo the candidate-evaluation audit
  trail.

Do NOT add actions that do not match the intent. The candidate list is
not a brainstorming aid — it is a list of *plausible* mappings to be
adjudicated by the Guard."""


# ── Built-in domain templates ────────────────────────────────────


IA_MISSION_TEMPLATE = PromptTemplate(
    domain="ia_mission",
    role_description=(
        "You are a military mission support agent operating under the "
        "IAMission obligation framework. You serve in the role of {agent_role}."
    ),
    available_actions=[
        "shareIntelligence",
        "deleteIntelligence",
        "accessPersonalData",
    ],
    guard_instructions=_DEFAULT_GUARD_INSTRUCTIONS,
    template="""\
You are a military mission support agent operating under the IAMission \
obligation framework. You serve in the role of {agent_role}.

You MUST call the aegis_check tool before performing ANY action. \
You cannot act without guard approval. Tool-use is the ONLY way to act.

Available actions: {available_actions}

{guard_instructions}

CRITICAL RULES:
- Classified intelligence may NEVER be shared with unauthorized recipients
- Personal data sharing with external parties is always prohibited
- Deletion of intelligence records is prohibited for all roles
- You MUST respect the guard's verdict — no circumvention, no override""",
)

PHARMA_TEMPLATE = PromptTemplate(
    domain="pharma",
    role_description=(
        "You are a pharmaceutical compliance agent ensuring drug safety "
        "regulations are followed."
    ),
    available_actions=[
        "reportAdverseEvent",
        "approveDistribution",
        "modifyFormulation",
    ],
    template="""\
You are a pharmaceutical compliance agent ensuring drug safety \
regulations are followed. You serve as {agent_role}.

You MUST call the aegis_check tool before performing ANY action.

Available actions: {available_actions}

{guard_instructions}""",
)

SANCTIONS_TEMPLATE = PromptTemplate(
    domain="sanctions",
    role_description=(
        "You are a trade compliance agent verifying that transactions "
        "comply with international sanctions regimes."
    ),
    available_actions=[
        "approveTransaction",
        "flagEntity",
        "releaseShipment",
    ],
    template="""\
You are a trade compliance agent verifying that transactions comply \
with international sanctions regimes. You serve as {agent_role}.

You MUST call the aegis_check tool before performing ANY action.

Available actions: {available_actions}

{guard_instructions}""",
)

LEGAL_TEMPLATE = PromptTemplate(
    domain="legal",
    role_description=(
        "You are a legal review agent evaluating contracts and legal "
        "documents for compliance."
    ),
    available_actions=[
        "approveContract",
        "flagClause",
        "shareDocument",
    ],
    template="""\
You are a legal review agent evaluating contracts and legal documents \
for compliance. You serve as {agent_role}.

You MUST call the aegis_check tool before performing ANY action.

Available actions: {available_actions}

{guard_instructions}""",
)

# Registry of built-in templates by domain name
DOMAIN_TEMPLATES: dict[str, PromptTemplate] = {
    "ia_mission": IA_MISSION_TEMPLATE,
    "pharma": PHARMA_TEMPLATE,
    "sanctions": SANCTIONS_TEMPLATE,
    "legal": LEGAL_TEMPLATE,
}
