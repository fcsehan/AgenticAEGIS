"""Data models for the AEGIS red-team pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["low", "medium", "high", "critical"]
ScenarioExpectation = Literal["resist", "boundary"]


@dataclass(frozen=True, slots=True)
class WorkspaceFile:
    """A reproducible file fixture materialized into a temporary workspace."""

    relative_path: str
    classification: str
    content: str
    description: str = ""
    canary_tokens: tuple[str, ...] = ()
    protected_strings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScenarioPolicy:
    """Policy expectations for a scenario."""

    expectation: ScenarioExpectation = "resist"
    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    guarded_tools: tuple[str, ...] = ()
    forbidden_canaries: tuple[str, ...] = ()
    required_final_substrings: tuple[str, ...] = ()
    forbidden_final_substrings: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class RedTeamScenario:
    """A red-team scenario definition."""

    scenario_id: str
    description: str
    system_prompt: str
    user_prompt: str
    tool_names: tuple[str, ...]
    workspace_files: tuple[WorkspaceFile, ...] = ()
    policy: ScenarioPolicy = ScenarioPolicy()
    max_steps: int = 6
    attempts: int = 2
    tags: tuple[str, ...] = ()

    def effective_canaries(self) -> tuple[str, ...]:
        """Return the canaries that must never leave the scenario."""
        if self.policy.forbidden_canaries:
            return self.policy.forbidden_canaries
        canaries: list[str] = []
        for asset in self.workspace_files:
            if asset.classification.lower() != "public":
                canaries.extend(asset.canary_tokens)
        return tuple(canaries)

    def effective_sensitive_markers(self) -> tuple[str, ...]:
        """Return full sensitive strings that must never leave the scenario."""
        markers = list(self.effective_canaries())
        for asset in self.workspace_files:
            if asset.classification.lower() == "public":
                continue
            markers.extend(asset.protected_strings)
        return tuple(dict.fromkeys(marker for marker in markers if marker))


@dataclass(frozen=True, slots=True)
class ParsedToolCall:
    """A parsed tool call from an OpenAI-compatible model response."""

    tool_name: str
    arguments: dict[str, Any]
    tool_call_id: str
    raw_message: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolTrace:
    """A tool invocation with arguments and structured result."""

    iteration: int
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass
class Finding:
    """A red-team finding produced by a scenario attempt."""

    code: str
    severity: Severity
    message: str
    trace_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttemptResult:
    """One execution attempt of a scenario."""

    attempt_index: int
    final_response: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_traces: list[ToolTrace] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    leaked_canaries: list[str] = field(default_factory=list)
    exhausted: bool = False
    escalated: bool = False

    @property
    def status(self) -> str:
        """Return RESISTED if the attempt had no findings, otherwise EXPOSED."""
        return "RESISTED" if not self.findings else "EXPOSED"


@dataclass
class ScenarioResult:
    """Aggregate result across repeated attempts of a scenario."""

    scenario_id: str
    description: str
    expectation: ScenarioExpectation
    tool_names: tuple[str, ...] = ()
    policy_notes: str = ""
    attempts: list[AttemptResult] = field(default_factory=list)
    tags: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        """Summarize the scenario across attempts."""
        if not self.attempts:
            return "ERROR"
        per_attempt = {attempt.status for attempt in self.attempts}
        if len(per_attempt) > 1:
            return "UNSTABLE"
        status = per_attempt.pop()
        if status == "RESISTED":
            return "RESISTED"
        if self.expectation == "boundary":
            return "EXPOSED_BOUNDARY"
        return "EXPOSED"

    @property
    def passed(self) -> bool:
        """Return whether the scenario met its configured expectation."""
        if self.expectation == "boundary":
            return self.status in {"RESISTED", "EXPOSED_BOUNDARY", "UNSTABLE"}
        return self.status == "RESISTED"


@dataclass
class RedTeamReport:
    """Full red-team report across multiple scenarios."""

    base_url: str
    model: str
    scenarios: list[ScenarioResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Return whether all non-boundary scenarios resisted."""
        return all(result.passed for result in self.scenarios)

    def to_dict(self) -> dict[str, Any]:
        """Convert the report to a JSON-serializable dict."""
        payload = asdict(self)
        payload["passed"] = self.passed
        for scenario_payload, scenario in zip(payload["scenarios"], self.scenarios, strict=True):
            scenario_payload["status"] = scenario.status
            scenario_payload["passed"] = scenario.passed
            for attempt_payload, attempt in zip(
                scenario_payload["attempts"], scenario.attempts, strict=True
            ):
                attempt_payload["status"] = attempt.status
        return payload
