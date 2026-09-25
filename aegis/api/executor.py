"""ActionExecutor — AEGIS-1003.

The structural enforcement of I5 (Non-Bypassability).  The LLM never gets
direct access to action executors.  It gets a single tool that internally
calls Guard.check() before any executor runs.

    LLM → aegis_check tool → ActionExecutor.execute()
                                  ├── guard.check(action) → PERMITTED?
                                  │     yes → run executor
                                  │     no  → return verdict, executor never called

If the LLM says "just do it without checking" — there is no tool for that.
The *only* tool available wraps the Guard.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision, ReasonType, Verdict
from aegis.hardening.permit import PermitStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Result of a guarded action execution.

    Attributes:
        verdict: The Guard verdict for this action.
        executed: Whether the executor was actually called.
        executor_result: Return value from the executor, if executed.
        error: Error message if the executor raised an exception.
    """

    verdict: Verdict
    executed: bool = False
    executor_result: Any = None
    error: str | None = None


# Type for executor functions: receives Action, returns any result.
ActionExecutor = Callable[[Action], Any]


class ActionExecutor:
    """Wraps Guard + action executors into a single tool.

    The LLM interacts ONLY through this class.  There is no way to
    execute an action without the Guard approving it first.

    Usage::

        executor = ActionExecutor(guard)
        executor.register("shareIntelligence", share_intel_fn)
        result = executor.execute(action)  # Guard.check() always runs first
    """

    def __init__(self, guard: Guard, *, permit_store: PermitStore | None = None) -> None:
        self._guard = guard
        self._executors: dict[str, ActionExecutor] = {}
        self._permit_store = permit_store

    def register(self, action_type: str, executor: ActionExecutor) -> None:
        """Register an executor for an action type.

        Each action type can have exactly one executor.
        """
        if action_type in self._executors:
            raise ValueError(f"Executor already registered for {action_type!r}")
        self._executors[action_type] = executor

    def execute(self, action: Action) -> ExecutionResult:
        """Execute an action — Guard.check() ALWAYS runs first.

        This is the ONLY path to action execution.

        Returns:
            ExecutionResult with verdict and optional executor output.
        """
        # Step 1: ALWAYS check with Guard — no bypass, no skip, no force
        verdict = self._guard.check(action)

        # Step 2: Only execute on PERMITTED
        if verdict.decision != Decision.PERMITTED:
            logger.info(
                "Action %s blocked: %s (%s)",
                action.action_type,
                verdict.decision.value,
                verdict.reason_type.value,
            )
            return ExecutionResult(verdict=verdict, executed=False)

        # Step 2b: AEGIS-1504 — consume permit token if store is active
        if self._permit_store is not None and verdict.permit_token_id:
            consumed = self._permit_store.consume(verdict.permit_token_id, action)
            if consumed is None:
                logger.warning(
                    "Permit token consumption failed for %s (D-004 safety → UNDECIDABLE)",
                    action.action_type,
                )
                safety_verdict = Verdict(
                    decision=Decision.UNDECIDABLE,
                    reason_type=ReasonType.INTERNAL_ERROR,
                    justification_chain=("Permit token consumption failed (D-004 safety)",),
                    action_type=action.action_type,
                    agent_id=action.agent_id,
                )
                return ExecutionResult(verdict=safety_verdict, executed=False)

        # Step 3: Find and run executor
        executor = self._executors.get(action.action_type)
        if executor is None:
            logger.warning(
                "No executor registered for %s (PERMITTED but not executable)",
                action.action_type,
            )
            return ExecutionResult(verdict=verdict, executed=False)

        try:
            result = executor(action)
            return ExecutionResult(
                verdict=verdict,
                executed=True,
                executor_result=result,
            )
        except Exception as e:
            logger.exception("Executor error for %s", action.action_type)
            return ExecutionResult(
                verdict=verdict,
                executed=False,
                error=f"Executor error: {e}",
            )

    def execute_from_dict(self, raw: dict[str, Any]) -> ExecutionResult:
        """Execute from a raw dict (as received from LLM tool call).

        Converts the dict to an Action and delegates to execute().
        """
        action = Action(
            action_type=raw.get("action_type", ""),
            agent_id=raw.get("agent_id", ""),
            proposition=raw.get("proposition", {}),
            context=raw.get("context", {}),
        )
        return self.execute(action)

    def as_tool(self) -> dict[str, Any]:
        """Generate LLM tool-use schema from the Guard's registry.

        Returns a dict compatible with both Claude Tool Use and
        OpenAI Function Calling formats.
        """
        action_types = self._guard._registry.action_types
        schemas: dict[str, Any] = {}

        for at in action_types:
            schema = self._guard._registry.get_schema(at)
            if schema:
                props: dict[str, Any] = {}
                for param in schema.parameters:
                    props[param.name] = {
                        "type": "string",
                        "description": f"Parameter: {param.name} (type: {param.type_name})",
                    }
                schemas[at] = props

        return {
            "name": "aegis_check",
            "description": (
                "Propose an action to the ethical guard for evaluation. "
                "You MUST call this tool before performing any action. "
                "The guard will respond with PERMITTED, FORBIDDEN, or UNDECIDABLE."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": action_types,
                        "description": "Type of action to perform",
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Your agent identifier",
                    },
                    "proposition": {
                        "type": "object",
                        "description": "Action parameters",
                    },
                },
                "required": ["action_type", "agent_id", "proposition"],
            },
        }

    def create_sub_executor(self) -> ActionExecutor:
        """Create a sub-executor sharing the same Guard but own executor registry.

        Sub-agents get the same Guard (same rules), but can register
        their own executors.
        """
        return ActionExecutor(self._guard, permit_store=self._permit_store)
