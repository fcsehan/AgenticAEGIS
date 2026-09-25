"""Intent-Action-Validator (Epic 31, AEGIS-3101..3107).

Pre-Guard validation layer that asks a *separate, independent* LLM
whether the formal action chosen by the agent-LLM is consistent with
the declared user intent. The validator-LLM has no tool access and a
strictly bounded prompt — its only output is one of three structured
verdicts (CONSISTENT / DRIFT / ESCALATE).

Architecture:

  Agent-LLM ── chooses Action + declares intent ──▶ orchestrator
       orchestrator ── invokes Validator ───────▶ Validator-LLM
              Validator-LLM ── ValidationVerdict ─▶ orchestrator
       orchestrator dispatches:
         • CONSISTENT → Guard.check / Guard.check_candidates as planned
         • DRIFT      → return to Agent-LLM with corrective hint
         • ESCALATE   → User-Confirmation-Loop (Epic 33) or hard-fail

The validator is *transport-agnostic*: it doesn't speak HTTP or any
concrete LLM provider. The orchestrator supplies a callback that takes
the rendered prompt and returns a ValidationVerdict. This keeps the
component fully unit-testable and lets each deployment plug in its own
LLM endpoint.

**Assurance level:** this layer is a heuristic based on structural
separation. An adversarial agent must also mislead a separate validator;
that separation is not a formal guarantee of independent errors. The
narrowest-action selection layer provides the formal, modeled component.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from aegis.guard.registry import ActionTypeRegistry


class ValidationDecision(Enum):
    """The three-way verdict from the Intent-Action-Validator."""

    CONSISTENT = "CONSISTENT"
    """Validator agrees that the chosen action matches the declared
    intent. Orchestrator continues with Guard.check / Guard.check_candidates."""

    DRIFT = "DRIFT"
    """Validator believes the chosen action does not match the declared
    intent. Orchestrator returns the verdict to the Agent-LLM with the
    correction hint and counts a retry. The retry budget is enforced by
    AEGIS-3104."""

    ESCALATE = "ESCALATE"
    """Validator could not decide (low confidence, ambiguous prompt,
    timeout). Orchestrator hands off to the User-Confirmation-Loop or
    fails closed depending on the policy from Epic 33."""


@dataclass(frozen=True, slots=True)
class ValidationVerdict:
    """Structured response from the Validator-LLM (AEGIS-3103).

    Attributes:
        decision: one of CONSISTENT / DRIFT / ESCALATE.
        reason: short human-readable explanation. Surfaced in audit
            and (when DRIFT) returned to the Agent-LLM.
        suggested_actions: for DRIFT, action types the validator
            considers a better fit. May be empty when the validator
            cannot suggest concrete alternatives.
        confidence: validator's self-reported confidence in [0, 1].
            ``None`` when the LLM did not return a confidence score.
    """

    decision: ValidationDecision
    reason: str = ""
    suggested_actions: tuple[str, ...] = ()
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class ValidatorRequest:
    """Input to the validator-LLM, rendered by the validator before the
    callback fires."""

    user_intent: str
    proposed_action_type: str
    action_description: str
    action_synonyms: tuple[str, ...] = ()
    confusable_alternatives: tuple[str, ...] = ()
    domain: str = ""


# Type alias for the validator-LLM bridge. Given a rendered request,
# produce a ValidationVerdict. The orchestrator wraps the actual LLM
# call (HTTP, in-process, mock) behind this signature.
ValidatorCallback = Callable[[ValidatorRequest], ValidationVerdict]


@dataclass(frozen=True, slots=True)
class ValidatorConfig:
    """Per-domain validator configuration (AEGIS-3106).

    Attributes:
        enabled: master switch. False = validator is bypassed entirely.
        timeout_seconds: how long to wait for a verdict.
        confidence_drift_threshold: confidence below this turns a
            CONSISTENT verdict into ESCALATE; e.g. 0.6 means "if the
            validator is < 60% sure, treat as escalate".
        max_drift_retries: retry budget for the Agent-LLM after a DRIFT
            verdict (AEGIS-3104). 0 = no retries (DRIFT becomes hard
            FORBIDDEN immediately).
        domain: identifier for audit/logging.
    """

    enabled: bool = True
    timeout_seconds: int = 5
    confidence_drift_threshold: float | None = None
    max_drift_retries: int = 1
    domain: str = ""


class ValidatorTimeout(TimeoutError):
    """Signal raised by a ValidatorCallback when the validator-LLM does
    not produce a verdict within ``timeout_seconds``."""


def render_validator_request(
    user_intent: str,
    proposed_action_type: str,
    registry: ActionTypeRegistry,
    *,
    domain: str = "",
) -> ValidatorRequest:
    """Build a ``ValidatorRequest`` from the orchestrator state.

    Pulls the action's description, synonyms and confusables out of the
    registry so the validator-LLM has the same disambiguation hints
    that the agent-LLM saw via the prompt template (AEGIS-2904). This
    is structural separation, not information starvation — the
    validator should evaluate the *same* metadata the agent saw.
    """
    description = registry.get_description(proposed_action_type) or ""
    synonyms = tuple(registry.get_synonyms(proposed_action_type))
    confusables = tuple(
        pair.other for pair in registry.get_confusables(proposed_action_type)
    )
    return ValidatorRequest(
        user_intent=user_intent,
        proposed_action_type=proposed_action_type,
        action_description=description,
        action_synonyms=synonyms,
        confusable_alternatives=confusables,
        domain=domain,
    )


@dataclass(frozen=True, slots=True)
class ValidatorOutcome:
    """What the orchestrator does next, derived from the verdict + config."""

    decision: ValidationDecision
    verdict: ValidationVerdict
    """The raw validator response."""

    retry_with_hint: str = ""
    """For DRIFT: the corrective hint to return to the Agent-LLM. Empty
    string when the orchestrator should not retry (e.g. retry budget
    exhausted)."""

    bypass_reason: str = ""
    """When the validator was bypassed by config, the reason for audit."""

    metadata: dict[str, str] = field(default_factory=dict)


class IntentActionValidator:
    """Pre-Guard validator (AEGIS-3102).

    Construct once per orchestrator session; reuse across many
    requests. Stateless w.r.t. application context (each ``validate``
    call is independent).
    """

    def __init__(
        self,
        config: ValidatorConfig,
        registry: ActionTypeRegistry,
        callback: ValidatorCallback,
    ) -> None:
        self._config = config
        self._registry = registry
        self._callback = callback

    @property
    def config(self) -> ValidatorConfig:
        return self._config

    def validate(
        self,
        user_intent: str,
        proposed_action_type: str,
        *,
        retries_so_far: int = 0,
    ) -> ValidatorOutcome:
        """Validate the agent-LLM's intent → action mapping.

        Returns a ``ValidatorOutcome`` describing what the orchestrator
        should do next. The validator never raises (timeout / LLM
        error are translated into ESCALATE).
        """
        if not self._config.enabled:
            return ValidatorOutcome(
                decision=ValidationDecision.CONSISTENT,
                verdict=ValidationVerdict(
                    decision=ValidationDecision.CONSISTENT,
                    reason="validator bypassed by config",
                ),
                bypass_reason="config_disabled",
            )

        if not user_intent:
            # Without a declared intent, the validator has nothing to
            # validate. Treat as ESCALATE so the orchestrator surfaces
            # the configuration error rather than silently passing.
            return ValidatorOutcome(
                decision=ValidationDecision.ESCALATE,
                verdict=ValidationVerdict(
                    decision=ValidationDecision.ESCALATE,
                    reason="user_intent missing — cannot validate",
                ),
                metadata={"reason": "no_intent_declared"},
            )

        request = render_validator_request(
            user_intent=user_intent,
            proposed_action_type=proposed_action_type,
            registry=self._registry,
            domain=self._config.domain,
        )

        try:
            verdict = self._callback(request)
        except ValidatorTimeout:
            return ValidatorOutcome(
                decision=ValidationDecision.ESCALATE,
                verdict=ValidationVerdict(
                    decision=ValidationDecision.ESCALATE,
                    reason=f"validator timed out after {self._config.timeout_seconds}s",
                ),
                metadata={"reason": "timeout"},
            )
        except Exception as exc:
            # Any other validator-side error → ESCALATE, never silently
            # accept. AEGIS-3107 (defense-in-depth against validator
            # bypass via injection).
            return ValidatorOutcome(
                decision=ValidationDecision.ESCALATE,
                verdict=ValidationVerdict(
                    decision=ValidationDecision.ESCALATE,
                    reason=f"validator error: {type(exc).__name__}",
                ),
                metadata={"reason": "exception", "type": type(exc).__name__},
            )

        # Confidence floor: even a CONSISTENT verdict escalates when
        # confidence is below threshold.
        if (
            verdict.decision == ValidationDecision.CONSISTENT
            and self._config.confidence_drift_threshold is not None
            and verdict.confidence is not None
            and verdict.confidence < self._config.confidence_drift_threshold
        ):
            return ValidatorOutcome(
                decision=ValidationDecision.ESCALATE,
                verdict=verdict,
                metadata={
                    "reason": "low_confidence",
                    "threshold": str(self._config.confidence_drift_threshold),
                },
            )

        if verdict.decision == ValidationDecision.DRIFT:
            return self._handle_drift(verdict, retries_so_far=retries_so_far)

        return ValidatorOutcome(decision=verdict.decision, verdict=verdict)

    def _handle_drift(
        self,
        verdict: ValidationVerdict,
        *,
        retries_so_far: int,
    ) -> ValidatorOutcome:
        """Drift-handling per AEGIS-3104.

        Returns DRIFT with retry_with_hint when retries are still
        available; otherwise returns ESCALATE with a clear reason so
        the orchestrator escalates rather than looping forever.
        """
        if retries_so_far >= self._config.max_drift_retries:
            return ValidatorOutcome(
                decision=ValidationDecision.ESCALATE,
                verdict=verdict,
                metadata={
                    "reason": "drift_retry_budget_exhausted",
                    "retries_so_far": str(retries_so_far),
                },
            )
        hint = verdict.reason or "validator detected intent-action drift"
        if verdict.suggested_actions:
            hint += f" — consider {', '.join(verdict.suggested_actions)}"
        return ValidatorOutcome(
            decision=ValidationDecision.DRIFT,
            verdict=verdict,
            retry_with_hint=hint,
            metadata={"retries_so_far": str(retries_so_far)},
        )
