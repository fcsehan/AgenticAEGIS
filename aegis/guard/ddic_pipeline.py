"""Evaluation pipeline for MELD/DDIC schema-version 2."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from aegis.engine.ddic_eval import DDICBeliefState, DDICRuntime, build_belief_state, evaluate_ddic_module
from aegis.engine.ddic_ir import DDICCompound, DDICModule, DDICSymbol, DDICTerm
from aegis.guard.action import Action
from aegis.guard.action_query import action_behavior, action_context, action_time
from aegis.guard.ddic_belief_state_adapter import verdict_from_belief_state
from aegis.guard.registry import ActionTypeRegistry
from aegis.guard.verdict import Decision, ReasonType, Verdict


class DDICEvaluationPipeline:
    """Guard evaluation pipeline for compiled DDIC v2 modules."""

    def __init__(
        self,
        module: DDICModule,
        registry: ActionTypeRegistry,
        *,
        enrichers: list[Callable[[Action], Action]] | None = None,
        normalize: bool = False,
    ) -> None:
        self._module = module
        self._registry = registry
        self._enrichers = enrichers or []
        self._normalize = normalize

    def run(self, action: Action) -> Verdict:
        if self._normalize:
            from aegis.hardening.normalize import normalize_action

            result = normalize_action(action, registry=self._registry)
            if result.rejected:
                return Verdict(
                    decision=Decision.UNDECIDABLE,
                    reason_type=ReasonType.INVALID_ACTION,
                    justification_chain=(f"Normalization rejected: {result.rejection_reason}",),
                    action_type=action.action_type,
                    agent_id=action.agent_id,
                )
            action = result.action

        violations = action.validate_limits()
        if violations:
            return Verdict(
                decision=Decision.UNDECIDABLE,
                reason_type=ReasonType.INVALID_ACTION,
                justification_chain=tuple(violations),
                action_type=action.action_type,
                agent_id=action.agent_id,
            )

        enriched = self._enrich(action)
        missing = self._check_required_context(enriched)
        if missing:
            return Verdict(
                decision=Decision.UNDECIDABLE,
                reason_type=ReasonType.MISSING_CONTEXT,
                justification_chain=tuple(f"Missing required context: {field}" for field in missing),
                action_type=enriched.action_type,
                agent_id=enriched.agent_id,
            )

        runtime = evaluate_ddic_module(self._module)
        scoped_state = self._scope_belief_state(runtime, enriched)
        in_domain = self._registry.is_known(enriched.action_type)
        if not scoped_state.active_beliefs and not scoped_state.unresolved_conflicts:
            return Verdict(
                decision=Decision.FORBIDDEN if in_domain else Decision.UNDECIDABLE,
                reason_type=ReasonType.CWA_NO_PERMISSION if in_domain else ReasonType.NO_JURISDICTION,
                action_type=enriched.action_type,
                agent_id=enriched.agent_id,
            )
        return verdict_from_belief_state(
            scoped_state,
            action_type=enriched.action_type,
            agent_id=enriched.agent_id,
        )

    def _enrich(self, action: Action) -> Action:
        result = action
        for enricher in self._enrichers:
            result = enricher(result)
        return result

    def _check_required_context(self, action: Action) -> list[str]:
        required = self._registry.required_context_fields(action.action_type)
        return [field for field in required if field not in action.context]

    def _scope_belief_state(self, runtime: DDICRuntime, action: Action) -> DDICBeliefState:
        target_behavior = self._action_behavior(action)
        target_context = self._action_context(action)
        scoped_runtime = replace(
            runtime,
            active_formulas=[
                derived
                for derived in runtime.active_formulas
                if _belief_matches_action(
                    derived.formula.agent,
                    derived.formula.behavior,
                    derived.formula.context,
                    action.agent_id,
                    target_behavior,
                    target_context,
                    runtime.world.relations,
                )
            ],
            defeated_formulas=[
                derived
                for derived in runtime.defeated_formulas
                if _belief_matches_action(
                    derived.formula.agent,
                    derived.formula.behavior,
                    derived.formula.context,
                    action.agent_id,
                    target_behavior,
                    target_context,
                    runtime.world.relations,
                )
            ],
        )
        return build_belief_state(scoped_runtime)

    def _action_behavior(self, action: Action) -> DDICTerm:
        # AEGIS-2313: delegate to the documented mapping module.
        return action_behavior(action, self._registry)

    @staticmethod
    def _action_context(action: Action) -> DDICTerm:
        # AEGIS-2313: delegate to the documented mapping module.
        return action_context(action)

    @staticmethod
    def _action_time(action: Action) -> DDICTerm:
        # AEGIS-2313: time threading. Callers that need Lex Posterior
        # dynamics should populate Action.context[TIME_KEY].
        return action_time(action)


def _belief_matches_action(
    belief_agent: object,
    belief_behavior: object,
    belief_context: object,
    action_agent: str,
    action_behavior: DDICTerm,
    action_context: DDICTerm,
    relations: tuple[Any, ...],
) -> bool:
    return (
        belief_agent == DDICSymbol(action_agent)
        and _overlaps(action_behavior, belief_behavior, relations, "behavior")
        and _overlaps(action_context, belief_context, relations, "context")
    )


def _term_from_value(value: Any) -> DDICTerm:
    if isinstance(value, str):
        return DDICSymbol(value)
    if isinstance(value, (tuple, list)) and value:
        head = value[0]
        if not isinstance(head, str):
            raise ValueError(f"Compound term head must be a string: {value!r}")
        return DDICCompound(head=head, args=tuple(_term_from_value(item) for item in value[1:]))
    return DDICSymbol(str(value))


def _overlaps(a: object, b: object, relations: tuple[Any, ...], namespace: str) -> bool:
    from aegis.engine.ddic_eval import _intersection, _is_top, _subsumes

    return (
        a == b
        or _is_top(a)
        or _is_top(b)
        or _subsumes(a, b, relations, namespace)
        or _subsumes(b, a, relations, namespace)
        or _intersection(a, b, relations, namespace) is not None
    )
