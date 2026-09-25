"""EvaluationPipeline — the unified evaluation chain.

  normalize → validate → enrich → check context → evaluate → decide

Supports both resolution strategies:
  - "legacy": v1 6-step DDIC algorithm (specificity + code prevalence)
  - "ddic":   v2 forward-chaining with priority/Lex Posterior defeat

Implements D-001 two-layer semantics:
  - Within a domain: absence of permission → FORBIDDEN (CWA)
  - Outside all domains: → UNDECIDABLE (no jurisdiction)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from aegis.deontic.norm_frame import NormFrame
from aegis.deontic.norm_status import NormStatus
from aegis.engine.ddic import DDICEngine
from aegis.engine.ddic_eval import (
    DDICBeliefState,
    DDICRuntime,
    DDICVerdict,
    build_belief_state,
    evaluate_ddic_module,
    evaluate_legacy_module,
)
from aegis.engine.ddic_ir import DDICCompound, DDICModule, DDICSymbol, DDICTerm
from aegis.guard.action import Action
from aegis.guard.action_query import action_behavior, action_context, action_time
from aegis.guard.registry import ActionTypeRegistry
from aegis.guard.verdict import Decision, ReasonType, Verdict
from aegis.tms.ltms import CWAEngine


class EvaluationPipeline:
    """The unified evaluation pipeline.

    Accepts either the legacy v1 constructor arguments (ddic + norms) or
    a compiled DDICModule.  When a module is provided, the pipeline dispatches
    to the appropriate evaluation strategy based on ``module.resolution_strategy``.

    Usage (unified, preferred)::

        pipeline = EvaluationPipeline.from_module(module, registry)
        verdict = pipeline.run(action)

    Usage (legacy, backward-compatible)::

        pipeline = EvaluationPipeline(ddic=ddic, registry=reg, norms=norms)
        verdict = pipeline.run(action)
    """

    def __init__(
        self,
        ddic: DDICEngine | None = None,
        registry: ActionTypeRegistry | None = None,
        norms: list[NormFrame] | None = None,
        *,
        module: DDICModule | None = None,
        inheritance: object | None = None,
        enrichers: list[Callable[[Action], Action]] | None = None,
        normalize: bool = False,
    ) -> None:
        self._ddic = ddic
        self._registry = registry or ActionTypeRegistry()
        self._norms = norms or []
        self._module = module
        self._inheritance = inheritance
        self._enrichers = enrichers or []
        self._cwa = CWAEngine()
        self._normalize = normalize

    @classmethod
    def from_module(
        cls,
        module: DDICModule,
        registry: ActionTypeRegistry,
        *,
        inheritance: object | None = None,
        enrichers: list[Callable[[Action], Action]] | None = None,
        normalize: bool = False,
    ) -> EvaluationPipeline:
        """Create a pipeline from a compiled DDICModule."""
        return cls(
            module=module,
            registry=registry,
            inheritance=inheritance,
            enrichers=enrichers,
            normalize=normalize,
        )

    def run(self, action: Action) -> Verdict:
        """Execute the full pipeline."""
        # Stage 0: Normalize (AEGIS-1505)
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

        # Stage 1: Validate (D-007)
        violations = action.validate_limits()
        if violations:
            return Verdict(
                decision=Decision.UNDECIDABLE,
                reason_type=ReasonType.INVALID_ACTION,
                justification_chain=tuple(violations),
                action_type=action.action_type,
                agent_id=action.agent_id,
            )

        # Stage 2: Enrich (D-010 hook — default: identity)
        enriched = self._enrich(action)

        # Stage 3: Check required context (D-010)
        missing = self._check_required_context(enriched)
        if missing:
            return Verdict(
                decision=Decision.UNDECIDABLE,
                reason_type=ReasonType.MISSING_CONTEXT,
                justification_chain=tuple(f"Missing required context: {f}" for f in missing),
                action_type=enriched.action_type,
                agent_id=enriched.agent_id,
            )

        in_domain = self._registry.is_known(enriched.action_type)

        # Stage 4+5: Evaluate + Decide — dispatch by strategy
        if self._module is not None:
            return self._evaluate_via_module(enriched, in_domain)

        # Legacy fallback: direct DDICEngine evaluation
        return self._evaluate_via_legacy_engine(enriched, in_domain)

    # ── Module-based evaluation (unified path) ──────────────────────

    def _evaluate_via_module(self, action: Action, in_domain: bool) -> Verdict:
        """Evaluate using the compiled DDICModule."""
        assert self._module is not None

        if self._module.resolution_strategy == "legacy":
            return self._evaluate_legacy_strategy(action, in_domain)
        return self._evaluate_ddic_strategy(action, in_domain)

    def _evaluate_legacy_strategy(self, action: Action, in_domain: bool) -> Verdict:
        """v1 6-step algorithm on DDICFormulas."""
        assert self._module is not None
        proposition = self._to_proposition(action)
        state = evaluate_legacy_module(
            self._module, proposition, action.agent_id, self._inheritance
        )
        # CWA: no applicable beliefs + in-domain → FORBIDDEN (D-001)
        if not state.active_beliefs and not state.unresolved_conflicts:
            chain = (
                f"No applicable norms for agent={action.agent_id!r}, "
                f"action={action.action_type!r}",
                "CWA: no permission found — FORBIDDEN" if in_domain else "Outside jurisdiction",
            )
            return Verdict(
                decision=Decision.FORBIDDEN if in_domain else Decision.UNDECIDABLE,
                reason_type=ReasonType.CWA_NO_PERMISSION if in_domain else ReasonType.NO_JURISDICTION,
                justification_chain=chain,
                action_type=action.action_type,
                agent_id=action.agent_id,
            )
        return self._verdict_from_belief_state(state, action, in_domain)

    def _evaluate_ddic_strategy(self, action: Action, in_domain: bool) -> Verdict:
        """v2 forward-chaining with priority/Lex Posterior defeat."""
        assert self._module is not None
        runtime = evaluate_ddic_module(self._module)
        scoped_state = self._scope_belief_state(runtime, action)

        if not scoped_state.active_beliefs and not scoped_state.unresolved_conflicts:
            return Verdict(
                decision=Decision.FORBIDDEN if in_domain else Decision.UNDECIDABLE,
                reason_type=ReasonType.CWA_NO_PERMISSION if in_domain else ReasonType.NO_JURISDICTION,
                action_type=action.action_type,
                agent_id=action.agent_id,
            )
        return self._verdict_from_belief_state(scoped_state, action, in_domain)

    # ── Legacy DDICEngine evaluation (backward-compatible) ──────────

    def _evaluate_via_legacy_engine(self, action: Action, in_domain: bool) -> Verdict:
        """Direct evaluation via the old DDICEngine (NormFrame-based)."""
        assert self._ddic is not None
        status = self._ddic.evaluate(
            proposition=self._to_proposition(action),
            agent=action.agent_id,
            norms=self._norms,
        )
        status = self._cwa.apply_cwa(status, in_domain=in_domain)
        return self._decide_from_norm_status(status, action)

    # ── Shared helpers ──────────────────────────────────────────────

    def _enrich(self, action: Action) -> Action:
        result = action
        for enricher in self._enrichers:
            result = enricher(result)
        return result

    def _check_required_context(self, action: Action) -> list[str]:
        required = self._registry.required_context_fields(action.action_type)
        return [f for f in required if f not in action.context]

    def _to_proposition(self, action: Action) -> tuple[Any, ...]:
        """Convert an action to a proposition tuple for DDIC."""
        parts: list[Any] = [action.action_type]
        schema = self._registry.get_schema(action.action_type)
        if schema and schema.parameters:
            for param in schema.parameters:
                if param.name in action.proposition:
                    parts.append(action.proposition[param.name])
        else:
            for key in sorted(action.proposition):
                parts.append(action.proposition[key])
        return tuple(parts)

    # ── Verdict adapters ────────────────────────────────────────────

    @staticmethod
    def _verdict_from_belief_state(
        state: DDICBeliefState, action: Action, in_domain: bool,
    ) -> Verdict:
        """Map DDICBeliefState to Verdict."""
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
                action_type=action.action_type,
                agent_id=action.agent_id,
            )
        if state.verdict == DDICVerdict.FORBIDDEN:
            return Verdict(
                decision=Decision.FORBIDDEN,
                reason_type=ReasonType.EXPLICIT_NORM,
                justification_chain=justification_chain,
                norms_applied=norms_applied,
                action_type=action.action_type,
                agent_id=action.agent_id,
            )

        # UNDECIDABLE
        reason = ReasonType.NO_JURISDICTION
        if state.unresolved_conflicts:
            reason = ReasonType.UNRESOLVED_CONFLICT
        elif in_domain:
            reason = ReasonType.CWA_NO_PERMISSION

        return Verdict(
            decision=Decision.UNDECIDABLE,
            reason_type=reason,
            justification_chain=justification_chain,
            norms_applied=norms_applied,
            action_type=action.action_type,
            agent_id=action.agent_id,
        )

    @staticmethod
    def _decide_from_norm_status(status: NormStatus, action: Action) -> Verdict:
        """Map NormStatus to Verdict (D-001 semantics) — legacy path."""
        norm_sources = tuple(n.source for n in status.winning_norms)

        if status.is_permitted():
            return Verdict(
                decision=Decision.PERMITTED,
                reason_type=_reason_type(status),
                justification_chain=status.justification_chain,
                norms_applied=norm_sources,
                action_type=action.action_type,
                agent_id=action.agent_id,
            )

        if status.is_forbidden() or status.is_obligatory():
            return Verdict(
                decision=Decision.FORBIDDEN,
                reason_type=_reason_type(status),
                justification_chain=status.justification_chain,
                norms_applied=norm_sources,
                action_type=action.action_type,
                agent_id=action.agent_id,
            )

        reason = ReasonType.NO_JURISDICTION
        if status.reason == "unresolved_conflict":
            reason = ReasonType.UNRESOLVED_CONFLICT
        elif status.reason == "cwa_no_permission":
            reason = ReasonType.CWA_NO_PERMISSION

        return Verdict(
            decision=Decision.UNDECIDABLE,
            reason_type=reason,
            justification_chain=status.justification_chain,
            norms_applied=norm_sources,
            action_type=action.action_type,
            agent_id=action.agent_id,
        )

    # ── v2 belief-state scoping ─────────────────────────────────────

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
        # AEGIS-2313: time threading. Used by future plan-evaluator and
        # by domains that rely on Lex Posterior dynamics.
        return action_time(action)


# ── Module-level helpers ────────────────────────────────────────────


def _reason_type(status: NormStatus) -> ReasonType:
    mapping: dict[str, ReasonType] = {
        "moral_axiom": ReasonType.MORAL_AXIOM,
        "specificity": ReasonType.EXPLICIT_NORM,
        "cross_code_prevalence": ReasonType.EXPLICIT_NORM,
        "cwa_no_permission": ReasonType.CWA_NO_PERMISSION,
        "unresolved_conflict": ReasonType.UNRESOLVED_CONFLICT,
    }
    return mapping.get(status.reason, ReasonType.EXPLICIT_NORM)


def _justification_chain(state: DDICBeliefState) -> list[str]:
    """Render belief state into the unified-pipeline justification chain.

    Mirrors ``ddic_belief_state_adapter._justification_chain`` so the v1-compiled
    and v2 paths produce structurally identical chains. AEGIS-2314:
    every derivation in the audit trail carries its premises *and*, when
    applicable, its defeat — complete vs partial — so an auditor can
    reconstruct exactly which rule lost to which testimony or higher-
    priority rule.
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


def _term_from_value(value: Any) -> DDICTerm:
    if isinstance(value, str):
        return DDICSymbol(value)
    if isinstance(value, (tuple, list)) and value:
        head = value[0]
        if not isinstance(head, str):
            raise ValueError(f"Compound term head must be a string: {value!r}")
        return DDICCompound(head=head, args=tuple(_term_from_value(item) for item in value[1:]))
    return DDICSymbol(str(value))
