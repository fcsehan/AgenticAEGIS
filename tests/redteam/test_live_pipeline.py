"""Live smoke test for the AEGIS red-team pipeline against LM Studio."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.guard import Guard
from aegis.redteam.pipeline import OpenAICompatibleLLMClient, RedTeamPipeline
from aegis.redteam.scenarios import build_default_scenarios

MELD_DIR = Path(__file__).parent.parent.parent / "aegis" / "domains" / "iamission"
LLM_CLIENT = OpenAICompatibleLLMClient(
    base_url="http://localhost:1234/v1",
    model="qwen/qwen3.8-27b",
    # Dense 27B model at ~10 tok/s: long red-team prompts exceed the 120 s default.
    timeout=600,
)


skip_no_llm = pytest.mark.skipif(
    not LLM_CLIENT.available(),
    reason="LM Studio not running at localhost:1234",
)


GUARD_BYPASS_CODES = frozenset({
    "UNGUARDED_TOOL_CALL",
    "FORBIDDEN_TOOL_USED",
    "PERMIT_ACTION_MISMATCH",
})


@skip_no_llm
def test_live_redteam_pipeline_runs() -> None:
    """The live pipeline should produce a structured report without crashing."""
    guard = Guard.from_meld_files(
        sorted(MELD_DIR.glob("*.meld")),
        code_prevalence=["IAMissionCode"],
    )
    pipeline = RedTeamPipeline(guard=guard, client=LLM_CLIENT)
    report = pipeline.run_scenarios(build_default_scenarios()[:1], attempts=1)

    assert len(report.scenarios) == 1
    attempt = report.scenarios[0].attempts[0]
    assert attempt.messages
    assert attempt.final_response or attempt.tool_traces or attempt.exhausted


@skip_no_llm
@pytest.mark.slow
def test_live_guard_perimeter_holds() -> None:
    """Structural proof: the Guard perimeter holds across all scenarios.

    Runs all scenarios (2 attempts each) and asserts the Guard invariant:
    no bypass-class findings (UNGUARDED_TOOL_CALL, FORBIDDEN_TOOL_USED,
    PERMIT_ACTION_MISMATCH). Text-channel findings (FINAL_RESPONSE_LEAK)
    are explicitly NOT asserted — they are perimeter boundaries, not Guard
    failures.
    """
    guard = Guard.from_meld_files(
        sorted(MELD_DIR.glob("*.meld")),
        code_prevalence=["IAMissionCode"],
    )
    pipeline = RedTeamPipeline(guard=guard, client=LLM_CLIENT)
    scenarios = build_default_scenarios()
    report = pipeline.run_scenarios(scenarios, attempts=2)

    assert len(report.scenarios) == len(scenarios)

    bypass_findings: list[str] = []
    for scenario_result in report.scenarios:
        for attempt in scenario_result.attempts:
            for finding in attempt.findings:
                if finding.code in GUARD_BYPASS_CODES:
                    bypass_findings.append(
                        f"{scenario_result.scenario_id} attempt {attempt.attempt_index}: "
                        f"{finding.code} — {finding.message}"
                    )

    assert bypass_findings == [], (
        f"Guard perimeter breached in {len(bypass_findings)} finding(s):\n"
        + "\n".join(f"  - {f}" for f in bypass_findings)
    )
