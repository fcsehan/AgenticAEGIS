"""AEGIS-1605: Host-Contract Tests.

Verifies that the host application correctly integrates AEGIS:
guard present, side-effect tools guarded, schema bounds enforced,
no bypass instructions in system prompts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from aegis.guard.registry import ActionTypeRegistry

Severity = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True, slots=True)
class ContractViolation:
    """A single host-contract violation."""

    code: str
    severity: Severity
    message: str
    tool_name: str = ""


class HostContractChecker:
    """Checks that a host application's tool configuration satisfies AEGIS contracts.

    Contracts enforced:
    - HC-001: At least one tool must be ``aegis_check`` (guard present).
    - HC-002: All side-effect tools must be in the guarded list.
    - HC-003: Tool schemas must declare bounded parameter types.
    - HC-004: No tool descriptions may contain bypass instructions.
    """

    def __init__(
        self,
        host_tools: list[dict[str, Any]],
        registry: ActionTypeRegistry | None = None,
        side_effect_tools: list[str] | None = None,
        guarded_tools: list[str] | None = None,
    ) -> None:
        self._host_tools = host_tools
        self._registry = registry
        self._side_effect_tools = set(side_effect_tools or [])
        self._guarded_tools = set(guarded_tools or [])

    def check_all(self) -> list[ContractViolation]:
        """Run all contract checks and return violations."""
        violations: list[ContractViolation] = []
        violations.extend(self._check_guard_present())
        violations.extend(self._check_side_effects_guarded())
        violations.extend(self._check_schema_bounds())
        violations.extend(self._check_no_bypass_instructions())
        return violations

    def _check_guard_present(self) -> list[ContractViolation]:
        """HC-001: At least one tool must be aegis_check."""
        tool_names = {self._tool_name(t) for t in self._host_tools}
        if "aegis_check" not in tool_names:
            return [ContractViolation(
                code="HC-001",
                severity="critical",
                message="No aegis_check tool found in host tool configuration.",
            )]
        return []

    def _check_side_effects_guarded(self) -> list[ContractViolation]:
        """HC-002: All declared side-effect tools must be guarded.

        Primary (HC-002): structural check — every side-effect tool must be
        in the explicit ``guarded_tools`` list.
        Advisory (HC-002a): text heuristic — tool description should mention
        the guard.
        """
        violations: list[ContractViolation] = []
        tool_names = {self._tool_name(t) for t in self._host_tools}

        for se_tool in sorted(self._side_effect_tools):
            if se_tool not in tool_names or se_tool == "aegis_check":
                continue

            # Primary: structural membership check
            if self._guarded_tools and se_tool not in self._guarded_tools:
                violations.append(ContractViolation(
                    code="HC-002",
                    severity="high",
                    message=(
                        f"Side-effect tool {se_tool!r} is not in the explicit "
                        "guarded_tools list."
                    ),
                    tool_name=se_tool,
                ))
            elif not self._guarded_tools:
                # Fallback when no guarded_tools declared: use text heuristic
                # as primary (backward compat)
                tool_def = next(
                    (t for t in self._host_tools if self._tool_name(t) == se_tool),
                    None,
                )
                if tool_def and not self._mentions_guard(tool_def):
                    violations.append(ContractViolation(
                        code="HC-002",
                        severity="high",
                        message=(
                            f"Side-effect tool {se_tool!r} is not guarded by "
                            "aegis_check."
                        ),
                        tool_name=se_tool,
                    ))

            # Advisory: text heuristic (always, even when structural passes)
            tool_def = next(
                (t for t in self._host_tools if self._tool_name(t) == se_tool),
                None,
            )
            if tool_def and not self._mentions_guard(tool_def):
                violations.append(ContractViolation(
                    code="HC-002a",
                    severity="low",
                    message=(
                        f"Side-effect tool {se_tool!r} description does not mention "
                        "the AEGIS guard (advisory)."
                    ),
                    tool_name=se_tool,
                ))
        return violations

    def _check_schema_bounds(self) -> list[ContractViolation]:
        """HC-003: Tool schemas should declare bounded parameter types."""
        violations: list[ContractViolation] = []
        for tool in self._host_tools:
            name = self._tool_name(tool)
            fn = tool.get("function", tool)
            params = fn.get("parameters", {})
            properties = params.get("properties", {})

            for prop_name, prop_def in properties.items():
                if (
                    isinstance(prop_def, dict)
                    and prop_def.get("type") == "string"
                    and "maxLength" not in prop_def
                    and "enum" not in prop_def
                ):
                        violations.append(ContractViolation(
                            code="HC-003",
                            severity="low",
                            message=(
                                f"Tool {name!r} parameter {prop_name!r} "
                                f"is an unbounded string (no maxLength or enum)."
                            ),
                            tool_name=name,
                        ))
        return violations

    def _check_no_bypass_instructions(self) -> list[ContractViolation]:
        """HC-004: No tool descriptions should contain bypass instructions."""
        violations: list[ContractViolation] = []
        bypass_phrases = [
            "ignore the guard",
            "skip aegis_check",
            "bypass the guard",
            "without checking",
            "no need to check",
        ]

        for tool in self._host_tools:
            name = self._tool_name(tool)
            fn = tool.get("function", tool)
            desc = str(fn.get("description", "")).lower()

            for phrase in bypass_phrases:
                if phrase in desc:
                    violations.append(ContractViolation(
                        code="HC-004",
                        severity="critical",
                        message=(
                            f"Tool {name!r} description contains bypass instruction: "
                            f"{phrase!r}."
                        ),
                        tool_name=name,
                    ))
                    break  # One violation per tool is enough

        return violations

    @staticmethod
    def _tool_name(tool: dict[str, Any]) -> str:
        """Extract tool name from OpenAI-style tool definition."""
        fn = tool.get("function", tool)
        return str(fn.get("name", ""))

    @staticmethod
    def _mentions_guard(tool: dict[str, Any]) -> bool:
        """Check if a tool definition mentions AEGIS guard."""
        fn = tool.get("function", tool)
        desc = str(fn.get("description", "")).lower()
        return "aegis" in desc or "guard" in desc
