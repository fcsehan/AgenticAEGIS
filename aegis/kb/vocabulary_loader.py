"""Vocabulary Loader — extract ActionTypeSchemas from ActionVocab-Mts.

Per D-003: .meld files are the single source of truth for action types.
This loader extracts:
  - ActionTypes:      (isa X ActionType) or (isa X MissionActionType) etc.
  - ActionParameters: (actionParameter actionType paramName paramType)
  - RequiredContext:  (requiredContext actionType fieldName fieldType)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aegis.kb.knowledge_base import KnowledgeBase


@dataclass(frozen=True, slots=True)
class ActionParameter:
    """A parameter of an action type."""

    name: str
    type_name: str


@dataclass(frozen=True, slots=True)
class ContextRequirement:
    """A required context field for an action type."""

    name: str
    type_name: str


@dataclass
class ActionTypeSchema:
    """Schema for an action type, derived from .meld assertions.

    Attributes:
        name: The action type name (e.g. ``"shareIntelligence"``).
        type_collection: The collection this type belongs to.
        parameters: Action parameters declared via ``actionParameter``.
        required_context: Required context fields via ``requiredContext``.
        description: Optional NL gloss from ``actionDescription`` (AEGIS-2901).
        synonyms: NL phrases mapped to this action via ``actionSynonym``.
        confusables: Other action names declared as risky-to-confuse with
            this one via ``notToBeConfusedWith``.
        narrower_than: Other actions of which this one is a *specialisation*
            (direct ``narrowerThan`` edges; transitive closure happens at
            registry level).
        broader_than: Other actions that are *specialisations* of this one
            (direct ``broaderThan`` edges).
    """

    name: str
    type_collection: str = ""
    parameters: list[ActionParameter] = field(default_factory=list)
    required_context: list[ContextRequirement] = field(default_factory=list)
    description: str | None = None
    synonyms: list[str] = field(default_factory=list)
    confusables: list[str] = field(default_factory=list)
    narrower_than: list[str] = field(default_factory=list)
    broader_than: list[str] = field(default_factory=list)


# Collections that mark something as an action type.
_ACTION_TYPE_COLLECTIONS: frozenset[str] = frozenset(
    {
        "ActionType",
        "MissionActionType",
    }
)


class VocabularyLoader:
    """Extract action type schemas from a loaded KnowledgeBase.

    Usage::

        loader = VocabularyLoader(kb)
        schemas = loader.extract()
    """

    def __init__(self, kb: KnowledgeBase) -> None:
        self._kb = kb

    def extract(self) -> dict[str, ActionTypeSchema]:
        """Extract all ActionTypeSchemas from the KB.

        Returns a dict mapping action type name → schema.
        """
        schemas: dict[str, ActionTypeSchema] = {}

        # Find action types: (isa X Collection) where Collection ∈ _ACTION_TYPE_COLLECTIONS
        for collection in _ACTION_TYPE_COLLECTIONS:
            for fact in self._kb.query(("isa", "?x", collection)):
                if isinstance(fact, tuple) and len(fact) == 3:
                    name = str(fact[1])
                    if name not in schemas:
                        schemas[name] = ActionTypeSchema(name=name, type_collection=collection)

        # Extract parameters: (actionParameter actionType paramName paramType)
        for fact in self._kb.query(("actionParameter", "?action", "?param", "?type")):
            if isinstance(fact, tuple) and len(fact) == 4:
                action_name = str(fact[1])
                if action_name in schemas:
                    schemas[action_name].parameters.append(
                        ActionParameter(name=str(fact[2]), type_name=str(fact[3]))
                    )

        # Extract required context: (requiredContext actionType fieldName fieldType)
        for fact in self._kb.query(("requiredContext", "?action", "?field", "?type")):
            if isinstance(fact, tuple) and len(fact) == 4:
                action_name = str(fact[1])
                if action_name in schemas:
                    schemas[action_name].required_context.append(
                        ContextRequirement(name=str(fact[2]), type_name=str(fact[3]))
                    )

        # AEGIS-2903: extract Action-Substitution disambiguation metadata.
        # Schema entries are created lazily so a domain that declares a
        # description for an action without an (isa X ActionType) tuple
        # still surfaces a warning via the existing flow.
        for fact in self._kb.query(("actionDescription", "?action", "?text")):
            if isinstance(fact, tuple) and len(fact) == 3:
                action_name = str(fact[1])
                if action_name in schemas:
                    schemas[action_name].description = str(fact[2])

        for fact in self._kb.query(("actionSynonym", "?action", "?phrase")):
            if isinstance(fact, tuple) and len(fact) == 3:
                action_name = str(fact[1])
                if action_name in schemas:
                    schemas[action_name].synonyms.append(str(fact[2]))

        for fact in self._kb.query(("notToBeConfusedWith", "?a", "?b")):
            if isinstance(fact, tuple) and len(fact) == 3:
                left = str(fact[1])
                right = str(fact[2])
                if left in schemas:
                    schemas[left].confusables.append(right)

        for fact in self._kb.query(("narrowerThan", "?a", "?b")):
            if isinstance(fact, tuple) and len(fact) == 3:
                left = str(fact[1])
                right = str(fact[2])
                if left in schemas:
                    schemas[left].narrower_than.append(right)

        for fact in self._kb.query(("broaderThan", "?a", "?b")):
            if isinstance(fact, tuple) and len(fact) == 3:
                left = str(fact[1])
                right = str(fact[2])
                if left in schemas:
                    schemas[left].broader_than.append(right)

        return schemas
