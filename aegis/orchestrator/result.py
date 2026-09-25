"""OrchestratorResult — the outcome of a full LLM orchestration cycle."""

from __future__ import annotations

from dataclasses import dataclass, field

from aegis.guard.action import Action
from aegis.guard.verdict import Verdict


@dataclass
class OrchestratorResult:
    """Result of a full orchestration cycle.

    Attributes:
        final_response: The LLM's final text response to the user.
        actions_proposed: All actions the LLM proposed (including rejected ones).
        verdicts: All Guard verdicts issued during the cycle.
        actions_executed: Only the actions that were actually executed.
        rejection_count: How many times the Guard returned FORBIDDEN.
        escalated: Whether the LLM escalated to the human operator.
        messages: Full conversation history for audit.
    """

    final_response: str = ""
    actions_proposed: list[Action] = field(default_factory=list)
    verdicts: list[Verdict] = field(default_factory=list)
    actions_executed: list[Action] = field(default_factory=list)
    rejection_count: int = 0
    escalated: bool = False
    messages: list[dict[str, object]] = field(default_factory=list)
    output_sanitized: bool = False
    output_violations: tuple[str, ...] = ()
