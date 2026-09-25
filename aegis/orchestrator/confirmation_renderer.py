"""User-Confirmation-Loop view renderer (AEGIS-3303, Epic 33).

Renders a ``ConfirmationContext`` into a UI-agnostic ``ConfirmationView``
so any frontend (CLI, IDE, Web) can present the prompt without coupling
to the orchestrator. The renderer also provides the validation logic
for free-text restate responses (``ACTIVE_RESTATE`` echo format) so
the same word-overlap rule lives in one place.

The view does not contain UI-specific markup. Frontends translate
fields like ``risk_summary`` and ``alternatives`` into their native
widgets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aegis.guard.registry import ActionTypeRegistry
from aegis.orchestrator.confirmation_policy import (
    ConfirmationContext,
    ConfirmationPolicy,
    EchoFormat,
)


@dataclass(frozen=True, slots=True)
class ConfirmationView:
    """UI-agnostic confirmation prompt.

    The frontend chooses how to render each field; the orchestrator
    only guarantees that the *content* is consistent across calls.

    Attributes:
        echo_format: which interaction style to use.
        intent: the declared user intent (free text).
        proposed_action: the action_type the agent picked.
        action_description: NL description from MELD ``actionDescription``.
        risk_summary: short human-readable note about *why* this prompt
            is firing (e.g. "Multiple candidate actions matched.").
        alternatives: for ``EXPLICIT_SELECT``, the candidate set.
            Empty for the other formats.
        active_restate_hint: short instruction shown to the user in
            ``ACTIVE_RESTATE`` mode. Empty otherwise.
    """

    echo_format: EchoFormat
    intent: str
    proposed_action: str
    action_description: str
    risk_summary: str
    alternatives: tuple[str, ...] = ()
    active_restate_hint: str = ""


def render_confirmation_view(
    context: ConfirmationContext,
    policy: ConfirmationPolicy,
    registry: ActionTypeRegistry,
) -> ConfirmationView:
    """Build a ``ConfirmationView`` from the orchestrator state.

    The renderer is deterministic — same input, same output — and never
    raises. Errors in registry lookups degrade silently to empty strings
    so a malformed domain does not bring the user-confirmation flow
    down. AEGIS-3303 acceptance criterion: snapshot-stable per format.
    """
    description = registry.get_description(context.proposed_action_type) or ""
    risk_summary = _summarize_triggers(context)

    alternatives: tuple[str, ...] = ()
    active_hint = ""

    if policy.echo_format == EchoFormat.EXPLICIT_SELECT:
        alternatives = context.minimal_candidates or (context.proposed_action_type,)
    elif policy.echo_format == EchoFormat.ACTIVE_RESTATE:
        active_hint = (
            "Please restate the action you are authorising in your own words. "
            "The system checks that your restatement overlaps with the action's "
            "official description before accepting it."
        )

    return ConfirmationView(
        echo_format=policy.echo_format,
        intent=context.user_intent,
        proposed_action=context.proposed_action_type,
        action_description=description,
        risk_summary=risk_summary,
        alternatives=alternatives,
        active_restate_hint=active_hint,
    )


def _summarize_triggers(context: ConfirmationContext) -> str:
    """Render the trigger-set as a one-sentence human-readable summary."""
    if not context.triggers:
        return "Confirmation requested."
    parts: list[str] = []
    triggers = sorted(t.value for t in context.triggers)
    for value in triggers:
        if value == "MULTIPLE_MINIMAL_CANDIDATES":
            parts.append("Multiple candidate actions matched the user intent.")
        elif value == "VALIDATOR_DRIFT":
            parts.append("The intent-action validator reported drift.")
        elif value == "LOW_CONFIDENCE":
            parts.append("The validator reported low confidence.")
        elif value == "ACTION_SUBSTITUTION_DRIFT":
            parts.append("A substitution-drift detector flagged this action.")
    return " ".join(parts)


_WORD = re.compile(r"[A-Za-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD.finditer(text)}


def validate_active_restate(
    user_response: str,
    action_description: str,
    *,
    minimum_overlap: int = 2,
) -> bool:
    """Check whether ``user_response`` overlaps enough with
    ``action_description`` to count as a meaningful restatement.

    Default: at least ``minimum_overlap`` non-trivial tokens shared
    between the response and the description (excluding stopwords-ish
    short words ≤ 2 chars). Conservative tuning — we'd rather reject
    a thin "yes" than accept consent theater.

    Returns False on empty input or empty description; the orchestrator
    treats False as "user did not confirm".
    """
    if not user_response.strip():
        return False
    if not action_description.strip():
        return False
    response_tokens = {t for t in _tokens(user_response) if len(t) > 2}
    description_tokens = {t for t in _tokens(action_description) if len(t) > 2}
    overlap = response_tokens & description_tokens
    return len(overlap) >= minimum_overlap
