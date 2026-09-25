"""AEGIS-2719 (Epic 27) — OpenCode Plan-Adapter (Python reference).

This module is the **Python reference** for the OpenCode-side adapter
in ``opencode/packages/opencode/src/plugin/aegis.ts``. The TypeScript
hook is the deployment target; this Python module is the testable
artifact that codifies the conversion logic from "list of OpenCode
tool calls" to a Plan that ``Guard.plan_check`` can evaluate.

Why a Python reference: pytest is the project's authoritative test
harness. By writing the conversion in Python first and round-tripping
it through ``Guard.plan_check`` we lock in the action-mapping rules,
state-derivation policy, and step-aggregation semantics that the TS
adapter must match. Any drift between the two is a regression we can
detect with a fixture comparison.

The TypeScript adapter calls AEGIS via REST (POST /v1/plan_check
landed in the same ticket); the Python adapter calls Guard directly.
Both share the same conversion logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from aegis.guard.action import Action
from aegis.guard.plan import Plan, PlanStep, StateSnapshot
from aegis.guard.verdict import PlanVerdict


@dataclass(frozen=True, slots=True)
class OpenCodeToolCall:
    """One tool call from the OpenCode session log.

    Fields mirror the OpenCode ``tool.execute.before`` payload. Optional
    ``state_delta`` captures the post-state contribution this call
    declares — the TS adapter computes this from the tool's output;
    the Python reference uses an explicit field so the conversion is
    deterministic in tests.
    """

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""
    duration_s: float = 0.0
    state_delta: dict[str, Any] = field(default_factory=dict)


# ── Tool-name → action-type mapping ────────────────────────────────


_BASH_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\b.*-r", "deleteFile"),
    (r"\brm\b", "deleteFile"),
    (r"curl.*\|\s*(sh|bash)", "executeRemoteCode"),
    (r"wget.*\|\s*(sh|bash)", "executeRemoteCode"),
    (r"git\s+push\s+--force", "forceModifyRepository"),
    (r"git\s+push\s+-f\b", "forceModifyRepository"),
    (r"git\s+reset\s+--hard", "forceModifyRepository"),
    (r"docker\s+run\b", "executeContainer"),
    (r"\bchmod\b", "modifyPermissions"),
    (r"\bchown\b", "modifyPermissions"),
    # CI/CD patterns added for plan-level governance.
    (r"\bnpm\s+run\s+test\b", "testArtifact"),
    (r"\bpytest\b", "testArtifact"),
    (r"\bnpm\s+run\s+build\b", "buildArtifact"),
    (r"\bdocker\s+build\b", "buildArtifact"),
    (r"\bkubectl\s+apply\b", "deployArtifact"),
    (r"\bhelm\s+install\b", "deployArtifact"),
    (r"\bhelm\s+upgrade\b", "deployArtifact"),
]

_WRITE_PATTERNS: list[tuple[str, str]] = [
    (r"\.env(\b|\.)", "modifySensitiveConfig"),
    (r"credentials", "modifySensitiveConfig"),
    (r"\.pem$", "modifySensitiveConfig"),
    (r"\.key$", "modifySensitiveConfig"),
    (r"id_rsa", "modifySensitiveConfig"),
]

_DEFAULT_TOOL_MAP: dict[str, str] = {
    "read": "readFile",
    "glob": "searchFiles",
    "grep": "searchFiles",
    "webfetch": "accessExternalResource",
    "fetch": "accessExternalResource",
}

_UNKNOWN_ACTION = "unknownAction"


def map_tool_to_action_type(tool: str, args: dict[str, Any]) -> str:
    """Mirror of the TS resolveAction() logic.

    Mapping rule order: pattern matches first (bash + write), then the
    static default-mapping table, then ``unknownAction`` fallback. The
    TS adapter must follow the identical order; tests in this module
    cross-check the Python output against documented invariants.
    """
    haystack = " ".join(
        v if isinstance(v, str) else str(v) for v in args.values()
    )
    if tool in {"bash", "shell"}:
        for pattern, action_type in _BASH_PATTERNS:
            if re.search(pattern, haystack):
                return action_type
        return "executeCommand"
    if tool in {"write", "edit"}:
        for pattern, action_type in _WRITE_PATTERNS:
            if re.search(pattern, haystack):
                return action_type
        return "modifyFile"
    return _DEFAULT_TOOL_MAP.get(tool, _UNKNOWN_ACTION)


def build_proposition(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Project tool args into a Guard proposition.

    Keeps the keys the action-level adapter already uses (``path``,
    ``command``, ``url``) so plan-level evaluation reuses the same
    domain mapping. Unknown args are dropped — the proposition stays
    small and deterministic.
    """
    proposition: dict[str, Any] = {}
    if tool in {"read", "write", "edit"} and "file_path" in args:
        proposition["path"] = args["file_path"]
    elif tool in {"bash", "shell"} and "command" in args:
        proposition["command"] = args["command"]
    elif tool in {"webfetch", "fetch"} and "url" in args:
        proposition["url"] = args["url"]
    return proposition


# ── Tool-call list → Plan ──────────────────────────────────────────


def tool_calls_to_plan(
    tool_calls: list[OpenCodeToolCall],
    *,
    agent_id: str = "ciAgent",
    initial_state: dict[str, Any] | None = None,
    plan_id: str = "",
) -> Plan:
    """Convert a list of OpenCode tool calls into an AEGIS Plan.

    Each tool call becomes one PlanStep. ``call.state_delta`` becomes
    the step's ``post_state``; ``call.args`` feeds the action's
    proposition. ``initial_state`` (e.g. derived from the prior session
    state or the workspace classification manifest) seeds ``Plan.
    initial_state``.
    """
    steps: list[PlanStep] = []
    for index, call in enumerate(tool_calls):
        action_type = map_tool_to_action_type(call.tool, call.args)
        proposition = build_proposition(call.tool, call.args)
        steps.append(PlanStep(
            action=Action(
                action_type=action_type,
                agent_id=agent_id,
                proposition=proposition,
            ),
            step_id=call.call_id or f"step:{index}",
            scheduled_duration_s=call.duration_s,
            post_state=StateSnapshot(fields=dict(call.state_delta)),
        ))
    return Plan(
        steps=tuple(steps),
        initial_state=StateSnapshot(fields=dict(initial_state or {})),
        plan_id=plan_id,
    )


# ── Adapter façade ────────────────────────────────────────────────


@dataclass
class OpenCodePlanAdapter:
    """Reference Plan-adapter used by the OpenCode plug-in.

    Concrete usage::

        adapter = OpenCodePlanAdapter(guard)
        verdict = adapter.evaluate(tool_calls)
        if verdict.plan_decision == PlanDecision.PERMITTED:
            for call in tool_calls:
                run(call)        # caller's executor
    """

    guard: object  # actually aegis.guard.guard.Guard, kept loose for type-checking ergonomics
    agent_id: str = "ciAgent"

    def evaluate(
        self,
        tool_calls: list[OpenCodeToolCall],
        *,
        initial_state: dict[str, Any] | None = None,
        plan_id: str = "",
    ) -> PlanVerdict:
        """Convert and evaluate. Returns the PlanVerdict directly."""
        plan = tool_calls_to_plan(
            tool_calls,
            agent_id=self.agent_id,
            initial_state=initial_state,
            plan_id=plan_id,
        )
        return self.guard.plan_check(plan)  # type: ignore[attr-defined]


__all__ = [
    "OpenCodePlanAdapter",
    "OpenCodeToolCall",
    "build_proposition",
    "map_tool_to_action_type",
    "tool_calls_to_plan",
]
