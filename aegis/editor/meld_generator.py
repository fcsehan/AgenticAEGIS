"""AEGIS-1402: MELD Generation Engine.

Translates natural language + domain context → structured rule proposals.
The LLM produces tool calls (propose_rule), never raw MELD syntax.
Each proposal is deterministically converted to MELD via build_meld_expression().
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from aegis.editor.domain_model import DomainInfo
from aegis.editor.llm_provider import LLMClient
from aegis.editor.meld_writer import _MODALITY_TO_PREDICATE, _format_proposition

logger = logging.getLogger(__name__)

# ── Tool Schema for LLM ──────────────────────────────────────────

PROPOSE_RULE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "propose_rule",
        "description": (
            "Propose a deontic rule for the domain. Call this tool once for each "
            "rule you derive from the user's description. The rule will be "
            "verified by the AEGIS verification pipeline before acceptance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "modality": {
                    "type": "string",
                    "enum": ["OBLIGATORY", "FORBIDDEN", "PERMITTED"],
                    "description": "The deontic modality of the rule.",
                },
                "agent_role": {
                    "type": "string",
                    "description": (
                        "The agent role this rule applies to. "
                        "Must be one of the domain's defined roles, or '*' for all agents."
                    ),
                },
                "code_of_conduct": {
                    "type": "string",
                    "description": (
                        "The code of conduct this rule belongs to. "
                        "Must be one of the domain's defined codes, or empty for moral axioms."
                    ),
                },
                "action_type": {
                    "type": "string",
                    "description": (
                        "The action type governed by this rule "
                        "(e.g. 'shareIntelligence')."
                    ),
                },
                "proposition_parameters": {
                    "type": "object",
                    "description": "Additional parameters constraining the proposition.",
                    "additionalProperties": {"type": "string"},
                },
                "defeasible": {
                    "type": "boolean",
                    "description": (
                        "Whether this rule can be overridden by more "
                        "specific norms. Moral axioms are non-defeasible."
                    ),
                },
                "reasoning": {
                    "type": "string",
                    "description": "Your reasoning for why this rule is needed.",
                },
                "natural_language_summary": {
                    "type": "string",
                    "description": "A human-readable summary of the rule in the domain's language.",
                },
            },
            "required": [
                "modality",
                "agent_role",
                "action_type",
                "defeasible",
                "natural_language_summary",
            ],
        },
    },
}


# ── Data Models ───────────────────────────────────────────────────


@dataclass
class RuleProposal:
    """A structured rule proposal from the LLM."""

    modality: str
    agent_role: str
    code_of_conduct: str
    action_type: str
    proposition_parameters: dict[str, str]
    defeasible: bool
    reasoning: str
    natural_language_summary: str
    meld_expression: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "modality": self.modality,
            "agentRole": self.agent_role,
            "codeOfConduct": self.code_of_conduct,
            "actionType": self.action_type,
            "propositionParameters": self.proposition_parameters,
            "defeasible": self.defeasible,
            "reasoning": self.reasoning,
            "naturalLanguageSummary": self.natural_language_summary,
            "meldExpression": self.meld_expression,
        }


# ── MELD Expression Builder ──────────────────────────────────────


def build_meld_expression(proposal: RuleProposal) -> str:
    """Deterministically convert a RuleProposal to a MELD S-expression.

    Uses the same predicate mappings as meld_writer.py.
    Pure function — no side effects.
    """
    # Build proposition
    parts = [proposal.action_type]
    for key, value in sorted(proposal.proposition_parameters.items()):
        parts.append(f"{key} {value}")
    proposition = _format_proposition(" ".join(parts))

    if proposal.code_of_conduct:
        # WRT family (arity 3): code, agent, proposition
        predicate = _MODALITY_TO_PREDICATE.get(
            proposal.modality, "permittedToDo-WRT"
        )
        return f"({predicate} {proposal.code_of_conduct} {proposal.agent_role} ({proposition}))"
    else:
        # ToDo family (arity 2): agent, proposition (moral axiom)
        _axiom_predicates = {
            "OBLIGATORY": "oughtToDo",
            "FORBIDDEN": "forbiddenToDo",
            "PERMITTED": "permittedToDo",
        }
        predicate = _axiom_predicates.get(proposal.modality, "forbiddenToDo")
        return f"({predicate} {proposal.agent_role} ({proposition}))"


# ── System Prompt Builder ─────────────────────────────────────────


def _build_system_prompt(domain: DomainInfo) -> str:
    """Build a domain-aware system prompt for MELD authoring."""
    role_names = [r.name for r in domain.roles]
    code_names = [c.name for c in domain.codes]
    action_types = sorted({r.proposition.split()[0] for r in domain.rules if r.proposition})

    existing_rules: list[str] = []
    for rule in domain.rules[:20]:  # Cap examples
        existing_rules.append(
            f"  - {rule.modality}: {rule.agent_role} — {rule.proposition}"
            + (f" (under {rule.code})" if rule.code else "")
        )

    nl = chr(10)
    roles_block = (
        nl.join(f"- {r}" for r in role_names)
        if role_names
        else "- (none defined yet — suggest new role names)"
    )
    codes_block = (
        nl.join(f"- {c}" for c in code_names)
        if code_names
        else "- (none defined yet — suggest new code names)"
    )
    actions_block = (
        nl.join(f"- {a}" for a in action_types)
        if action_types
        else "- (none defined yet — define new action types)"
    )

    return f"""\
You are an AEGIS MELD authoring assistant. Your job is to \
translate natural language rule descriptions into structured \
deontic rule proposals.

You MUST use the propose_rule tool for each rule. Do NOT \
output raw MELD syntax.
Call propose_rule once per rule — multiple rules from a \
single description is expected.

## Domain Context: {domain.name}
{domain.description or "No description."}

## Available Roles
{roles_block}

## Available Codes of Conduct
{codes_block}

## Known Action Types
{actions_block}

## Existing Rules (for context)
{chr(10).join(existing_rules) if existing_rules else "  (no rules yet)"}

## MELD Grammar Reference (34 symbols)
The 9 deontic predicates:
- oughtToDo(agent, proposition) — obligation without code
- forbiddenToDo(agent, proposition) — prohibition without code
- permittedToDo(agent, proposition) — permission without code
- oughtToDo-WRT(code, agent, proposition) — obligation under code
- forbiddenToDo-WRT(code, agent, proposition) — prohibition under code
- permittedToDo-WRT(code, agent, proposition) — permission under code
- oughtToBe(proposition) — state obligation
- forbiddenToBe(proposition) — state prohibition
- permittedToBe(proposition) — state permission

## Guidelines
1. Use existing roles and codes when possible
2. Defeasible=true for most rules; false only for absolute moral axioms
3. Use specific proposition parameters to narrow scope
4. Provide clear natural_language_summary in the domain's language
5. Include reasoning explaining why this rule is necessary"""


# ── Generator ─────────────────────────────────────────────────────


class MeldGenerator:
    """Generates structured rule proposals from natural language descriptions.

    Usage::

        gen = MeldGenerator(client, domain)
        proposals = gen.generate("Agents must report adverse events within 24h")
        # proposals is a list of RuleProposal with MELD expressions
    """

    def __init__(self, client: LLMClient, domain: DomainInfo) -> None:
        self._client = client
        self._domain = domain
        self._system_prompt = _build_system_prompt(domain)

    def generate(
        self,
        description: str,
        *,
        roles: list[str] | None = None,
        action_types: list[str] | None = None,
    ) -> list[RuleProposal]:
        """Generate rule proposals from a natural language description.

        Args:
            description: Natural language description of the rules.
            roles: Optional filter — only generate rules for these roles.
            action_types: Optional filter — only generate rules for these action types.

        Returns:
            List of RuleProposal, each with a MELD expression.
        """
        user_content = description
        if roles:
            user_content += f"\n\nFocus on roles: {', '.join(roles)}"
        if action_types:
            user_content += f"\n\nFocus on action types: {', '.join(action_types)}"

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]

        response = self._client.chat(messages, tools=[PROPOSE_RULE_TOOL])
        return self._extract_proposals(response)

    def refine_proposal(
        self,
        proposal: RuleProposal,
        feedback: str,
    ) -> list[RuleProposal]:
        """Refine a proposal based on user feedback.

        Returns one or more updated proposals.
        """
        messages = [
            {"role": "system", "content": self._system_prompt},
            {
                "role": "user",
                "content": (
                    f"I previously proposed this rule:\n"
                    f"  Modality: {proposal.modality}\n"
                    f"  Agent: {proposal.agent_role}\n"
                    f"  Action: {proposal.action_type}\n"
                    f"  Summary: {proposal.natural_language_summary}\n\n"
                    f"Feedback: {feedback}\n\n"
                    f"Please propose an updated rule using the propose_rule tool."
                ),
            },
        ]

        response = self._client.chat(messages, tools=[PROPOSE_RULE_TOOL])
        return self._extract_proposals(response)

    def _extract_proposals(self, response: dict[str, Any]) -> list[RuleProposal]:
        """Extract RuleProposals from an LLM response."""
        proposals: list[RuleProposal] = []
        message = response.get("choices", [{}])[0].get("message", {})

        tool_calls = message.get("tool_calls", [])
        for tc in tool_calls:
            fn = tc.get("function", {})
            if fn.get("name") != "propose_rule":
                continue
            raw_args = fn.get("arguments", "{}")
            args: dict[str, Any] = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

            proposal = RuleProposal(
                modality=args.get("modality", "FORBIDDEN"),
                agent_role=args.get("agent_role", "*"),
                code_of_conduct=args.get("code_of_conduct", ""),
                action_type=args.get("action_type", ""),
                proposition_parameters=args.get("proposition_parameters", {}),
                defeasible=args.get("defeasible", True),
                reasoning=args.get("reasoning", ""),
                natural_language_summary=args.get("natural_language_summary", ""),
            )
            proposal.meld_expression = build_meld_expression(proposal)
            proposals.append(proposal)

        return proposals
