"""Default ConfirmationPolicy per domain (AEGIS-3305, Epic 33).

Concrete defaults for the six bundled domains. Reviewer-Sign-Off
discipline (per-domain expert) is captured in DECISION_LOG D-017.
The defaults are deliberately *strict for high-risk domains* and
*lenient for low-risk dev tooling* to match the actual operational
context:

- iamission, pharma, sanctions: ACTIVE_RESTATE + FAIL_CLOSED, broad
  trigger set. Consent must be active and meaningful.
- legal: EXPLICIT_SELECT + ESCALATE_TO_REVIEWER on timeout. Legal
  reviews are slow; we let them escalate rather than hard-fail.
- devops: PASSIVE_YES_NO + short timeout, minimum trigger set. The
  cost of friction is higher than the cost of an extra confirmation
  (compared to military intel where the inverse holds).
- ifc: only fires on ``MULTIPLE_MINIMAL_CANDIDATES`` (Epic 32). IFC
  controls information-flow channels; we don't want to disturb the
  flow with frequent prompts.

These are *defaults*. Domain authors override per deployment via
configuration (mechanism is the responsibility of the deployment
layer, not this module).
"""

from __future__ import annotations

from aegis.orchestrator.confirmation_policy import (
    ConfirmationPolicy,
    EchoFormat,
    TimeoutAction,
    TriggerCondition,
)

# Trigger sets shared between several domains.
_HIGH_RISK_TRIGGERS = (
    TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,
    TriggerCondition.VALIDATOR_DRIFT,
    TriggerCondition.LOW_CONFIDENCE,
    TriggerCondition.ACTION_SUBSTITUTION_DRIFT,
)

_MEDIUM_RISK_TRIGGERS = (
    TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,
    TriggerCondition.VALIDATOR_DRIFT,
)

_NARROW_TRIGGERS = (
    TriggerCondition.MULTIPLE_MINIMAL_CANDIDATES,
)


IAMISSION_DEFAULT_POLICY = ConfirmationPolicy(
    triggers=_HIGH_RISK_TRIGGERS,
    timeout_seconds=120,
    timeout_action=TimeoutAction.FAIL_CLOSED,
    echo_format=EchoFormat.ACTIVE_RESTATE,
    domain="iamission",
)

PHARMA_DEFAULT_POLICY = ConfirmationPolicy(
    triggers=_HIGH_RISK_TRIGGERS,
    timeout_seconds=120,
    timeout_action=TimeoutAction.FAIL_CLOSED,
    echo_format=EchoFormat.ACTIVE_RESTATE,
    domain="pharma",
)

SANCTIONS_DEFAULT_POLICY = ConfirmationPolicy(
    triggers=_HIGH_RISK_TRIGGERS,
    timeout_seconds=120,
    timeout_action=TimeoutAction.FAIL_CLOSED,
    echo_format=EchoFormat.ACTIVE_RESTATE,
    domain="sanctions",
)

LEGAL_DEFAULT_POLICY = ConfirmationPolicy(
    triggers=_MEDIUM_RISK_TRIGGERS,
    timeout_seconds=300,  # legal reviews are slower
    timeout_action=TimeoutAction.ESCALATE_TO_REVIEWER,
    echo_format=EchoFormat.EXPLICIT_SELECT,
    domain="legal",
)

DEVOPS_DEFAULT_POLICY = ConfirmationPolicy(
    triggers=_MEDIUM_RISK_TRIGGERS,
    timeout_seconds=30,  # CI/CD context — short window
    timeout_action=TimeoutAction.FAIL_CLOSED,
    echo_format=EchoFormat.PASSIVE_YES_NO,
    domain="devops",
)

IFC_DEFAULT_POLICY = ConfirmationPolicy(
    triggers=_NARROW_TRIGGERS,
    timeout_seconds=30,
    timeout_action=TimeoutAction.FAIL_CLOSED,
    echo_format=EchoFormat.EXPLICIT_SELECT,
    domain="ifc",
)


DOMAIN_DEFAULT_POLICIES: dict[str, ConfirmationPolicy] = {
    "iamission": IAMISSION_DEFAULT_POLICY,
    "pharma": PHARMA_DEFAULT_POLICY,
    "sanctions": SANCTIONS_DEFAULT_POLICY,
    "legal": LEGAL_DEFAULT_POLICY,
    "devops": DEVOPS_DEFAULT_POLICY,
    "ifc": IFC_DEFAULT_POLICY,
}


def default_policy_for(domain: str) -> ConfirmationPolicy:
    """Return the default ``ConfirmationPolicy`` for ``domain``.

    Falls back to a minimal disabled policy for unknown domains so the
    User-Confirmation-Loop never fires unexpectedly. Domain authors
    that want explicit confirmation behaviour must declare a non-empty
    triggers tuple.
    """
    return DOMAIN_DEFAULT_POLICIES.get(domain, ConfirmationPolicy(domain=domain))
