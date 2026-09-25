"""Tests for the Intent-Action-Validator (Epic 31, AEGIS-3101..3107)."""

from __future__ import annotations

from aegis.guard.registry import ActionTypeRegistry
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import MeldLoader
from aegis.orchestrator.intent_action_validator import (
    IntentActionValidator,
    ValidationDecision,
    ValidationVerdict,
    ValidatorConfig,
    ValidatorRequest,
    ValidatorTimeout,
    render_validator_request,
)


def _registry() -> ActionTypeRegistry:
    kb = KnowledgeBase()
    loader = MeldLoader(kb)
    loader.load_string(
        """
        (case TestVocabMt)
        (isa readDiagnosis ActionType)
        (isa readPatientRecord ActionType)
        (actionDescription readDiagnosis "Reads only the diagnostic conclusion section.")
        (actionDescription readPatientRecord "Reads the entire patient record.")
        (actionSynonym readDiagnosis "view diagnosis")
        (notToBeConfusedWith readDiagnosis readPatientRecord)
        """,
        file="test.meld",
    )
    kb.freeze()
    return ActionTypeRegistry.from_kb(kb)


def _consistent_callback(request: ValidatorRequest) -> ValidationVerdict:
    return ValidationVerdict(
        decision=ValidationDecision.CONSISTENT,
        reason="ok",
        confidence=0.95,
    )


def _drift_callback(request: ValidatorRequest) -> ValidationVerdict:
    return ValidationVerdict(
        decision=ValidationDecision.DRIFT,
        reason="agent picked broader action",
        suggested_actions=("readDiagnosis",),
        confidence=0.85,
    )


def _escalate_callback(request: ValidatorRequest) -> ValidationVerdict:
    return ValidationVerdict(
        decision=ValidationDecision.ESCALATE,
        reason="ambiguous request",
        confidence=0.4,
    )


class TestRenderValidatorRequest:
    def test_pulls_description_and_synonyms_from_registry(self) -> None:
        request = render_validator_request(
            user_intent="show me the diagnosis",
            proposed_action_type="readDiagnosis",
            registry=_registry(),
            domain="iamission",
        )
        assert request.user_intent == "show me the diagnosis"
        assert request.proposed_action_type == "readDiagnosis"
        assert "diagnostic" in request.action_description
        assert "view diagnosis" in request.action_synonyms
        assert "readPatientRecord" in request.confusable_alternatives
        assert request.domain == "iamission"

    def test_empty_metadata_for_unknown_action(self) -> None:
        request = render_validator_request(
            user_intent="x",
            proposed_action_type="ghostAction",
            registry=_registry(),
        )
        assert request.action_description == ""
        assert request.action_synonyms == ()
        assert request.confusable_alternatives == ()


class TestBypass:
    def test_disabled_validator_returns_consistent_with_bypass_reason(self) -> None:
        validator = IntentActionValidator(
            config=ValidatorConfig(enabled=False),
            registry=_registry(),
            callback=_drift_callback,  # would normally trigger drift
        )
        outcome = validator.validate(
            user_intent="show me the diagnosis",
            proposed_action_type="readPatientRecord",
        )
        assert outcome.decision == ValidationDecision.CONSISTENT
        assert outcome.bypass_reason == "config_disabled"


class TestMissingIntent:
    def test_empty_intent_escalates(self) -> None:
        validator = IntentActionValidator(
            config=ValidatorConfig(),
            registry=_registry(),
            callback=_consistent_callback,
        )
        outcome = validator.validate(
            user_intent="",
            proposed_action_type="readDiagnosis",
        )
        assert outcome.decision == ValidationDecision.ESCALATE
        assert outcome.metadata["reason"] == "no_intent_declared"


class TestConsistentPath:
    def test_consistent_verdict_passes_through(self) -> None:
        validator = IntentActionValidator(
            config=ValidatorConfig(),
            registry=_registry(),
            callback=_consistent_callback,
        )
        outcome = validator.validate(
            user_intent="show me the diagnosis",
            proposed_action_type="readDiagnosis",
        )
        assert outcome.decision == ValidationDecision.CONSISTENT
        assert outcome.verdict.confidence == 0.95


class TestDriftPath:
    def test_drift_with_retries_left(self) -> None:
        validator = IntentActionValidator(
            config=ValidatorConfig(max_drift_retries=2),
            registry=_registry(),
            callback=_drift_callback,
        )
        outcome = validator.validate(
            user_intent="show me the diagnosis",
            proposed_action_type="readPatientRecord",
            retries_so_far=0,
        )
        assert outcome.decision == ValidationDecision.DRIFT
        assert "readDiagnosis" in outcome.retry_with_hint
        assert "broader" in outcome.retry_with_hint

    def test_drift_with_no_retries_escalates(self) -> None:
        validator = IntentActionValidator(
            config=ValidatorConfig(max_drift_retries=0),
            registry=_registry(),
            callback=_drift_callback,
        )
        outcome = validator.validate(
            user_intent="show me the diagnosis",
            proposed_action_type="readPatientRecord",
            retries_so_far=0,
        )
        assert outcome.decision == ValidationDecision.ESCALATE
        assert outcome.metadata["reason"] == "drift_retry_budget_exhausted"

    def test_drift_after_budget_exhausted_escalates(self) -> None:
        validator = IntentActionValidator(
            config=ValidatorConfig(max_drift_retries=1),
            registry=_registry(),
            callback=_drift_callback,
        )
        outcome = validator.validate(
            user_intent="show me the diagnosis",
            proposed_action_type="readPatientRecord",
            retries_so_far=1,  # one retry already consumed
        )
        assert outcome.decision == ValidationDecision.ESCALATE


class TestEscalatePath:
    def test_escalate_verdict_passes_through(self) -> None:
        validator = IntentActionValidator(
            config=ValidatorConfig(),
            registry=_registry(),
            callback=_escalate_callback,
        )
        outcome = validator.validate(
            user_intent="ambiguous request",
            proposed_action_type="readDiagnosis",
        )
        assert outcome.decision == ValidationDecision.ESCALATE


class TestConfidenceThreshold:
    def test_low_confidence_consistent_becomes_escalate(self) -> None:
        """AEGIS-3106: confidence_drift_threshold turns a "consistent
        but unsure" verdict into ESCALATE so the orchestrator can hand
        off to user confirmation."""
        def low_confidence_callback(request: ValidatorRequest) -> ValidationVerdict:
            return ValidationVerdict(
                decision=ValidationDecision.CONSISTENT,
                reason="probably ok",
                confidence=0.3,
            )

        validator = IntentActionValidator(
            config=ValidatorConfig(confidence_drift_threshold=0.5),
            registry=_registry(),
            callback=low_confidence_callback,
        )
        outcome = validator.validate(
            user_intent="something",
            proposed_action_type="readDiagnosis",
        )
        assert outcome.decision == ValidationDecision.ESCALATE
        assert outcome.metadata["reason"] == "low_confidence"

    def test_high_confidence_consistent_passes(self) -> None:
        validator = IntentActionValidator(
            config=ValidatorConfig(confidence_drift_threshold=0.5),
            registry=_registry(),
            callback=_consistent_callback,  # confidence=0.95
        )
        outcome = validator.validate(
            user_intent="show me the diagnosis",
            proposed_action_type="readDiagnosis",
        )
        assert outcome.decision == ValidationDecision.CONSISTENT


class TestErrorPaths:
    def test_timeout_callback_yields_escalate(self) -> None:
        def timeout_callback(request: ValidatorRequest) -> ValidationVerdict:
            raise ValidatorTimeout

        validator = IntentActionValidator(
            config=ValidatorConfig(timeout_seconds=10),
            registry=_registry(),
            callback=timeout_callback,
        )
        outcome = validator.validate(
            user_intent="x",
            proposed_action_type="readDiagnosis",
        )
        assert outcome.decision == ValidationDecision.ESCALATE
        assert outcome.metadata["reason"] == "timeout"

    def test_callback_exception_yields_escalate(self) -> None:
        """AEGIS-3107: an exception in the validator path must NOT
        silently accept the action — fail-closed via ESCALATE."""
        def exploding_callback(request: ValidatorRequest) -> ValidationVerdict:
            raise RuntimeError("validator crashed")

        validator = IntentActionValidator(
            config=ValidatorConfig(),
            registry=_registry(),
            callback=exploding_callback,
        )
        outcome = validator.validate(
            user_intent="x",
            proposed_action_type="readDiagnosis",
        )
        assert outcome.decision == ValidationDecision.ESCALATE
        assert outcome.metadata["reason"] == "exception"
        assert outcome.metadata["type"] == "RuntimeError"


class TestStructuralSeparation:
    def test_validator_request_carries_no_action_payload(self) -> None:
        """AEGIS-3107 architectural invariant: the validator only sees
        the intent + action-type + disambiguation metadata. It never
        sees the actual proposition payload because that would expand
        its attack surface (validator could be used as an exfiltration
        oracle). This test pins the contract via the request type."""
        request = render_validator_request(
            user_intent="x",
            proposed_action_type="readDiagnosis",
            registry=_registry(),
        )
        # The request must NOT have a 'proposition' or 'context' field.
        # Locking the Pydantic-style schema in via attribute access.
        assert not hasattr(request, "proposition")
        assert not hasattr(request, "context")
        assert not hasattr(request, "action_arguments")
