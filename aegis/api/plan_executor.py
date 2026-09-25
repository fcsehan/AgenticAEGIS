"""AEGIS-2711 (Epic 27) — PlanActionExecutor.

Plan-level analogue of ``aegis.api.executor.ActionExecutor``: the
single, structurally-non-bypassable path from a Plan to executed
steps. Internally calls ``Guard.plan_check`` first, issues a
``PlanPermitToken``, and then walks the plan step-by-step, validating
each step's hash against the token before invoking the registered
executor.

Threat model:
- Action substitution mid-plan: caught by per-step hash compare.
- Step reordering / addition: the post-2710 PlanPipeline already
  catches this at plan_check time, but if a caller tries to execute
  a *different* plan with the same token, the hash tuple mismatches.
- Token replay across plans: each plan issues a fresh token; the
  store is single-issue per plan_check.
- Runtime executor failure: token hard-invalidated, remaining steps
  not executed (fail-fast), audit emits PLAN_EXECUTION_ABORTED.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.plan import Plan
from aegis.guard.verdict import PlanDecision, PlanVerdict
from aegis.hardening.permit import (
    PlanPermitStore,
    canonical_action_hash,
)

logger = logging.getLogger(__name__)


StepExecutor = Callable[[Action], Any]


@dataclass(frozen=True, slots=True)
class PlanStepExecutionRecord:
    """Outcome of one executed (or attempted) step."""

    step_index: int
    action_type: str
    executed: bool
    result: Any = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PlanExecutionResult:
    """Aggregate result of ``PlanActionExecutor.execute_plan``."""

    plan_verdict: PlanVerdict
    executed_step_records: tuple[PlanStepExecutionRecord, ...] = ()
    aborted: bool = False
    abort_reason: str = ""
    plan_token_id: str = ""

    @property
    def all_steps_executed(self) -> bool:
        return (
            self.plan_verdict.plan_decision == PlanDecision.PERMITTED
            and not self.aborted
            and len(self.executed_step_records) == len(
                self.plan_verdict.per_step_verdicts
            )
        )


class PlanActionExecutor:
    """Wraps Guard + step-executors into a plan-aware executor.

    Usage::

        plan_exec = PlanActionExecutor(guard)
        plan_exec.register("runTests", run_tests_fn)
        plan_exec.register("deploy", deploy_fn)
        result = plan_exec.execute_plan(plan)

    Like ``ActionExecutor``, this class is the single entry point —
    callers cannot reach the registered step-executors directly.
    """

    def __init__(
        self,
        guard: Guard,
        *,
        plan_permit_store: PlanPermitStore | None = None,
    ) -> None:
        self._guard = guard
        self._executors: dict[str, StepExecutor] = {}
        self._plan_permit_store = plan_permit_store or PlanPermitStore()

    def register(self, action_type: str, executor: StepExecutor) -> None:
        """Register a step-executor for ``action_type``.

        Each action_type can have at most one executor. Conflicting
        registrations raise ``ValueError`` so configuration mistakes
        surface at startup rather than at execute-time.
        """
        if action_type in self._executors:
            raise ValueError(
                f"Step executor already registered for {action_type!r}"
            )
        self._executors[action_type] = executor

    def execute_plan(self, plan: Plan) -> PlanExecutionResult:
        """Run ``plan`` end-to-end.

        Stages (none can be skipped — structural I5):
        1. ``Guard.plan_check(plan)`` — always runs first.
        2. On non-PERMITTED: return PlanExecutionResult with the
           verdict and zero step records. No step executor is called.
        3. On PERMITTED: issue a ``PlanPermitToken`` carrying the
           per-step hash tuple of the plan that the Guard just
           approved.
        4. Iterate steps in order. Per step:
           a. ``PlanPermitStore.consume_plan_step(token, idx, action)``
              — validates the step's hash matches what the Guard
              approved. Mismatch → hard-invalidate, abort.
           b. Find the registered executor for ``action_type``. If
              missing → log + abort with PLAN_EXECUTION_ABORTED.
           c. Run the executor. Exceptions → invalidate token,
              return partial result.
        """
        verdict = self._guard.plan_check(plan)
        if verdict.plan_decision != PlanDecision.PERMITTED:
            logger.info(
                "Plan blocked or undecidable: %s (%s)",
                verdict.plan_decision.value, verdict.reason_summary,
            )
            return PlanExecutionResult(plan_verdict=verdict)

        # Issue token. The hash tuple is recomputed from the plan
        # the Guard just saw — same Plan object, deterministic
        # canonicalisation.
        step_hashes = tuple(
            canonical_action_hash(step.action) for step in plan.steps
        )
        token = self._plan_permit_store.issue(plan.plan_id, step_hashes)

        records: list[PlanStepExecutionRecord] = []
        for index, step in enumerate(plan.steps):
            consumed = self._plan_permit_store.consume_plan_step(
                token.token_id, index, step.action,
            )
            if consumed is None:
                logger.warning(
                    "Plan token consumption failed at step %d (%s) — "
                    "D-004 fail-closed, aborting plan",
                    index, step.action.action_type,
                )
                return PlanExecutionResult(
                    plan_verdict=verdict,
                    executed_step_records=tuple(records),
                    aborted=True,
                    abort_reason=(
                        f"plan_token_consume_failed:step={index}:"
                        f"{step.action.action_type}"
                    ),
                    plan_token_id=token.token_id,
                )

            executor = self._executors.get(step.action.action_type)
            if executor is None:
                logger.warning(
                    "No step executor for %s at step %d — aborting plan",
                    step.action.action_type, index,
                )
                self._plan_permit_store.invalidate(token.token_id)
                return PlanExecutionResult(
                    plan_verdict=verdict,
                    executed_step_records=tuple(records),
                    aborted=True,
                    abort_reason=(
                        f"no_step_executor:step={index}:"
                        f"{step.action.action_type}"
                    ),
                    plan_token_id=token.token_id,
                )

            try:
                result = executor(step.action)
                records.append(
                    PlanStepExecutionRecord(
                        step_index=index,
                        action_type=step.action.action_type,
                        executed=True,
                        result=result,
                    )
                )
            except Exception as e:
                logger.exception(
                    "Step executor raised at step %d (%s) — aborting plan",
                    index, step.action.action_type,
                )
                self._plan_permit_store.invalidate(token.token_id)
                records.append(
                    PlanStepExecutionRecord(
                        step_index=index,
                        action_type=step.action.action_type,
                        executed=False,
                        error=f"executor_error: {e}",
                    )
                )
                return PlanExecutionResult(
                    plan_verdict=verdict,
                    executed_step_records=tuple(records),
                    aborted=True,
                    abort_reason=(
                        f"executor_error:step={index}:"
                        f"{step.action.action_type}"
                    ),
                    plan_token_id=token.token_id,
                )

        return PlanExecutionResult(
            plan_verdict=verdict,
            executed_step_records=tuple(records),
            aborted=False,
            plan_token_id=token.token_id,
        )


__all__ = [
    "PlanActionExecutor",
    "PlanExecutionResult",
    "PlanStepExecutionRecord",
]
