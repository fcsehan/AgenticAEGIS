"""Adapter from DDIC v2 belief states to guard Verdicts."""

from __future__ import annotations

from aegis.engine.ddic_eval import DDICBeliefState, DDICRuntime, DDICVerdict, build_belief_state
from aegis.guard.verdict import Decision, ReasonType, Verdict


def verdict_from_ddic_runtime(
    runtime: DDICRuntime,
    *,
    action_type: str = "",
    agent_id: str = "",
) -> Verdict:
    """Build a guard Verdict from a DDIC v2 runtime."""
    return verdict_from_belief_state(
        build_belief_state(runtime),
        action_type=action_type,
        agent_id=agent_id,
    )


def verdict_from_belief_state(
    state: DDICBeliefState,
    *,
    action_type: str = "",
    agent_id: str = "",
) -> Verdict:
    """Map DDIC v2 belief-state semantics to the guard Verdict model."""
    norms_applied = tuple(
        belief.rule_id or belief.formula.source_ref for belief in state.active_beliefs
    )
    justification_chain = tuple(_justification_chain(state))

    if state.verdict == DDICVerdict.PERMITTED:
        return Verdict(
            decision=Decision.PERMITTED,
            reason_type=ReasonType.EXPLICIT_NORM,
            justification_chain=justification_chain,
            norms_applied=norms_applied,
            action_type=action_type,
            agent_id=agent_id,
        )

    if state.verdict == DDICVerdict.FORBIDDEN:
        return Verdict(
            decision=Decision.FORBIDDEN,
            reason_type=ReasonType.EXPLICIT_NORM,
            justification_chain=justification_chain,
            norms_applied=norms_applied,
            action_type=action_type,
            agent_id=agent_id,
        )

    return Verdict(
        decision=Decision.UNDECIDABLE,
        reason_type=(
            ReasonType.UNRESOLVED_CONFLICT if state.unresolved_conflicts else ReasonType.NO_JURISDICTION
        ),
        justification_chain=justification_chain,
        norms_applied=norms_applied,
        action_type=action_type,
        agent_id=agent_id,
    )


def _justification_chain(state: DDICBeliefState) -> list[str]:
    """Render belief state into a human-auditable justification chain.

    Order: active beliefs (the verdict-bearing premises), defeats (which
    derivation lost to which testimony/rule, complete vs partial), then
    unresolved conflicts. AEGIS-2306 acceptance criterion #6.
    """
    chain: list[str] = []
    for belief in state.active_beliefs:
        chain.append(
            f"{belief.derivation_id}: {belief.formula.layer.value}:{belief.formula.mode.value}:{belief.formula.polarity.value}"
        )
    for event in state.defeats:
        defeating_ref = event.defeating_rule_id or event.defeating_formula_id
        chain.append(
            f"defeat:{event.reason.value}:{event.mode}:"
            f"{event.defeated_derivation_id}<-{defeating_ref}"
        )
    for conflict in state.unresolved_conflicts:
        chain.append(
            f"conflict:{conflict.conflict_type.value}:{conflict.left_formula_id}:{conflict.right_formula_id}"
        )
    return chain
