"""AEGIS red-team pipeline for adversarial prompt and tool-use evaluation."""

from .models import (
    AttemptResult,
    Finding,
    ParsedToolCall,
    RedTeamReport,
    RedTeamScenario,
    ScenarioPolicy,
    ScenarioResult,
    WorkspaceFile,
)
from .pipeline import OpenAICompatibleLLMClient, RedTeamPipeline
from .scenarios import (
    DEFAULT_DOMAIN_DIR,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    build_default_scenarios,
)

__all__ = [
    "AttemptResult",
    "DEFAULT_DOMAIN_DIR",
    "DEFAULT_MODEL",
    "DEFAULT_SYSTEM_PROMPT",
    "Finding",
    "OpenAICompatibleLLMClient",
    "ParsedToolCall",
    "RedTeamPipeline",
    "RedTeamReport",
    "RedTeamScenario",
    "ScenarioPolicy",
    "ScenarioResult",
    "WorkspaceFile",
    "build_default_scenarios",
]
