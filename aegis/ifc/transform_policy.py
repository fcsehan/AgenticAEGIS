"""AEGIS-1705: Transformation Policy Engine.

Checks whether information transformations (summarize, extract, compare,
reclassify) are permitted given the source/target classifications and
the intended recipient.

All policy lives in InformationFlowDeonticRulesMt.meld — this engine
only translates transformation requests into Guard-checkable Actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aegis.guard.action import Action

if TYPE_CHECKING:
    from aegis.guard.guard import Guard
    from aegis.guard.verdict import Verdict

# Map transformation types to their corresponding action types
_TRANSFORMATION_ACTION_MAP: dict[str, str] = {
    "summarization": "summarizeInformation",
    "summarize": "summarizeInformation",
    "extraction": "extractFacts",
    "extract": "extractFacts",
    "comparison": "compareInformation",
    "compare": "compareInformation",
    "reclassification": "classifyInformation",
    "reclassify": "classifyInformation",
    "export": "exportInformation",
}


class TransformPolicy:
    """Policy-checked information transformations.

    Usage::

        engine = TransformPolicy(guard)
        verdict = engine.check_transformation(
            transformation_type="summarization",
            source_classifications=["secret"],
            target_classification="public",
            target_recipient="externalService",
            agent_id="agent-007",
        )
        if verdict.decision == Decision.FORBIDDEN:
            # Cannot summarize secret content for public audience
            ...
    """

    def __init__(self, guard: Guard) -> None:
        self._guard = guard

    def check_transformation(
        self,
        transformation_type: str,
        source_classifications: list[str],
        target_classification: str,
        target_recipient: str,
        agent_id: str,
    ) -> Verdict:
        """Check whether a transformation is permitted.

        Builds an Action from the transformation parameters and delegates
        to the Guard for evaluation against MELD norms.
        """
        action_type = _TRANSFORMATION_ACTION_MAP.get(
            transformation_type.lower(),
            "summarizeInformation",
        )

        # Use the highest source classification for the check
        source_classification = _highest_classification(source_classifications)

        proposition: dict[str, str] = {
            "sourceClassification": source_classification,
            "targetClassification": target_classification,
            "recipient": target_recipient,
        }

        # Some action types don't use all fields — the Guard/DDIC
        # matches on what's present in the proposition
        if action_type == "classifyInformation":
            proposition = {
                "sourceClassification": source_classification,
                "targetClassification": target_classification,
            }
        elif action_type == "compareInformation":
            proposition = {
                "sourceClassification": source_classification,
                "purpose": "internalAnalysis",
            }

        action = Action(
            action_type=action_type,
            agent_id=agent_id,
            proposition=proposition,
        )
        return self._guard.check(action)


_CLASSIFICATION_ORDER: dict[str, int] = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "secret": 3,
    "topsecret": 4,
    "top_secret": 4,
    "top-secret": 4,
}


def _highest_classification(classifications: list[str]) -> str:
    """Return the highest classification from a list."""
    if not classifications:
        return "public"
    return max(
        classifications,
        key=lambda c: _CLASSIFICATION_ORDER.get(c.lower(), 0),
    )
