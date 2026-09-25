"""AEGIS-1503: Safe Refusal Templates.

Provides safe, information-minimal refusal messages for FORBIDDEN and
UNDECIDABLE verdicts.  User-facing messages never leak norm names,
data classifications, or proposition values.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aegis.guard.verdict import ReasonType, Verdict


class _ReasonCategory(Enum):
    """Broad refusal categories for user-facing messages."""

    POLICY = "policy"
    JURISDICTION = "jurisdiction"
    CONFLICT = "conflict"
    INPUT = "input"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class RefusalTemplate:
    """A single refusal template.

    Attributes:
        reason_type: The :class:`ReasonType` this template covers.
        user_message: Safe, generic message for the end user.
        llm_feedback: More specific message fed back to the LLM for retry.
    """

    reason_type: ReasonType
    user_message: str
    llm_feedback: str


_TEMPLATES: dict[ReasonType, RefusalTemplate] = {
    ReasonType.EXPLICIT_NORM: RefusalTemplate(
        reason_type=ReasonType.EXPLICIT_NORM,
        user_message="This action is not permitted under the applicable policy.",
        llm_feedback=(
            "Your proposed action was explicitly forbidden by a governing norm. "
            "Propose an alternative that does not violate the applicable rules."
        ),
    ),
    ReasonType.CWA_NO_PERMISSION: RefusalTemplate(
        reason_type=ReasonType.CWA_NO_PERMISSION,
        user_message="This action is not permitted under the applicable policy.",
        llm_feedback=(
            "No permission was found for this action in the loaded domain. "
            "Under closed-world assumption, absence of permission means forbidden."
        ),
    ),
    ReasonType.NO_JURISDICTION: RefusalTemplate(
        reason_type=ReasonType.NO_JURISDICTION,
        user_message="This action falls outside the scope of the current policy framework.",
        llm_feedback=(
            "The action type is not covered by any loaded domain. "
            "Escalate to a human operator or propose a recognized action."
        ),
    ),
    ReasonType.UNRESOLVED_CONFLICT: RefusalTemplate(
        reason_type=ReasonType.UNRESOLVED_CONFLICT,
        user_message="This action could not be evaluated due to a policy conflict.",
        llm_feedback=(
            "Conflicting norms apply to this action and could not be resolved. "
            "Escalate to a human operator for clarification."
        ),
    ),
    ReasonType.INTERNAL_ERROR: RefusalTemplate(
        reason_type=ReasonType.INTERNAL_ERROR,
        user_message="This action could not be evaluated at this time.",
        llm_feedback=(
            "An internal error occurred during evaluation. "
            "Do not retry the same action. Escalate to a human operator."
        ),
    ),
    ReasonType.EVALUATION_TIMEOUT: RefusalTemplate(
        reason_type=ReasonType.EVALUATION_TIMEOUT,
        user_message="This action could not be evaluated at this time.",
        llm_feedback=(
            "Evaluation timed out. Simplify the action or escalate."
        ),
    ),
    ReasonType.INVALID_ACTION: RefusalTemplate(
        reason_type=ReasonType.INVALID_ACTION,
        user_message="The proposed action was malformed and could not be processed.",
        llm_feedback=(
            "The action input failed validation. Check that action_type, agent_id, "
            "and proposition are well-formed and within size limits."
        ),
    ),
    ReasonType.MISSING_CONTEXT: RefusalTemplate(
        reason_type=ReasonType.MISSING_CONTEXT,
        user_message="Additional context is required to evaluate this action.",
        llm_feedback=(
            "Required context fields are missing for this action type. "
            "Provide the necessary context and retry."
        ),
    ),
    ReasonType.MORAL_AXIOM: RefusalTemplate(
        reason_type=ReasonType.MORAL_AXIOM,
        user_message="This action is prohibited by a non-negotiable ethical principle.",
        llm_feedback=(
            "A non-defeasible moral axiom forbids this action. "
            "No override is possible. Do not retry. Inform the user."
        ),
    ),
}


class RefusalRegistry:
    """Registry of safe refusal templates for all :class:`ReasonType` values."""

    def __init__(self) -> None:
        self._templates: dict[ReasonType, RefusalTemplate] = dict(_TEMPLATES)

    def get(self, reason_type: ReasonType) -> RefusalTemplate:
        """Return the template for *reason_type*.

        Falls back to INTERNAL_ERROR if no template is registered.
        """
        return self._templates.get(
            reason_type,
            self._templates[ReasonType.INTERNAL_ERROR],
        )

    def render_for_user(self, verdict: Verdict) -> str:
        """Render a safe user-facing message from *verdict*."""
        template = self.get(verdict.reason_type)
        return template.user_message

    def render_for_llm(self, verdict: Verdict) -> str:
        """Render feedback for the LLM from *verdict*."""
        template = self.get(verdict.reason_type)
        return template.llm_feedback
