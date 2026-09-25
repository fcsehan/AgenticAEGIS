"""Revision-bound action/plan regression scenarios, persisted separately from norms."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from aegis.api.server import PlanCheckRequest
from aegis.editor.api import CheckRequest, get_state
from aegis.editor.mediation import authorize_editor
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.plan import Plan, PlanStep, PlanViolation, StateSnapshot

router = APIRouter(prefix="/api/domains", dependencies=[Depends(authorize_editor)])


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=200)
    expected: Literal["PERMITTED", "FORBIDDEN", "UNDECIDABLE"]
    action: CheckRequest | None = None
    plan: PlanCheckRequest | None = None


class ScenarioSet(BaseModel):
    revision: str
    scenarios: list[Scenario] = Field(max_length=200)


def evaluate_plan(
    domain_id: str,
    body: PlanCheckRequest,
    *,
    guard: Guard | None = None,
    revision: str | None = None,
) -> dict[str, Any]:
    state = get_state()
    guard = guard or state.guards.get(domain_id)
    if guard is None:
        raise HTTPException(409, "No compiled guard for this domain")
    plan = Plan(
        steps=tuple(
            PlanStep(
                action=Action(
                    action_type=s.action_type,
                    agent_id=s.agent_id,
                    proposition=s.proposition,
                    context=s.context,
                ),
                step_id=s.step_id,
                scheduled_duration_s=s.scheduled_duration_s,
                pre_state=StateSnapshot(s.pre_state),
                post_state=StateSnapshot(s.post_state),
            )
            for s in body.steps
        ),
        initial_state=StateSnapshot(body.initial_state),
        plan_id=body.plan_id,
    )
    verdict = guard.plan_check(plan)
    return {
        "revision": revision or state.domains[domain_id].revision,
        "decision": verdict.plan_decision.value,
        "reasonSummary": verdict.reason_summary,
        "evaluationMode": verdict.evaluation_mode,
        "steps": [
            {
                "decision": v.decision.value,
                "reasonType": v.reason_type.value,
                "justificationChain": list(v.justification_chain),
                "normsApplied": list(v.norms_applied),
            }
            for v in verdict.per_step_verdicts
        ],
        "violations": [
            {
                "type": v.violation_type.value,
                "stepIndex": v.step_index,
                "constraintId": v.constraint_id,
                "detail": v.detail,
            }
            for v in cast(tuple[PlanViolation, ...], verdict.violations)
        ],
    }


def scenario_path(domain_id: str) -> Path:
    source = get_state().sources.get(domain_id)
    if source is None:
        raise HTTPException(404, "Load a source domain first")
    source.load()  # Includes the storage boundary/integrity check.
    if source.load()[1] != get_state().domains[domain_id].revision:
        raise HTTPException(409, "External source changed; reopen project before testing")
    if (source.directory / "scenarios.json").is_symlink():
        raise HTTPException(409, "Scenario symlinks are not supported")
    return source.directory / "scenarios.json"


@router.post("/{domain_id}/plan_check")
def check_plan(domain_id: str, body: PlanCheckRequest) -> dict[str, Any]:
    scenario_path(domain_id)
    return evaluate_plan(domain_id, body)


@router.get("/{domain_id}/scenarios")
def get_scenarios(domain_id: str) -> dict[str, Any]:
    path = scenario_path(domain_id)
    if not path.exists():
        return {"scenarios": [], "revision": get_state().domains[domain_id].revision}
    result: dict[str, Any] = json.loads(path.read_text())
    return result


@router.put("/{domain_id}/scenarios")
def save_scenarios(domain_id: str, body: ScenarioSet) -> dict[str, Any]:
    path = scenario_path(domain_id)
    if body.revision != get_state().domains[domain_id].revision:
        raise HTTPException(409, "Domain revision changed")
    if len({s.id for s in body.scenarios}) != len(body.scenarios):
        raise HTTPException(422, "Scenario IDs must be unique")
    if any((s.action is None) == (s.plan is None) for s in body.scenarios):
        raise HTTPException(422, "Each scenario needs exactly one action or plan")
    result = body.model_dump(by_alias=True)
    atomic_json(path, result)
    path.with_name("test-results.json").unlink(missing_ok=True)
    return result


@router.post("/{domain_id}/scenarios/run")
def run_scenarios(domain_id: str) -> dict[str, Any]:
    data = ScenarioSet.model_validate(get_scenarios(domain_id))
    state = get_state()
    guard = state.guards.get(domain_id)
    if guard is None:
        raise HTTPException(409, "No compiled guard")
    revision = state.domains[domain_id].revision
    results = []
    for scenario in data.scenarios:
        if scenario.action:
            a = scenario.action
            verdict = guard.check(
                Action(
                    action_type=a.action_type,
                    agent_id=a.agent,
                    proposition=a.parameters,
                    context=a.context,
                )
            )
            actual = verdict.decision.value
            details: dict[str, Any] = {
                "reasonType": verdict.reason_type.value,
                "justificationChain": list(verdict.justification_chain),
            }
        elif scenario.plan:
            details = evaluate_plan(domain_id, scenario.plan)
            actual = details["decision"]
        else:
            raise HTTPException(422, "Invalid saved scenario")
        results.append(
            {
                "id": scenario.id,
                "expected": scenario.expected,
                "actual": actual,
                "passed": actual == scenario.expected,
                "details": details,
            }
        )
    from aegis.editor.revision_governance import digest

    result = {
        "scenarioHash": digest(get_scenarios(domain_id)),
        "revision": revision,
        "passed": bool(results) and all(r["passed"] for r in results),
        "results": results,
    }
    if state.domains[domain_id].revision != revision:
        raise HTTPException(409, "Domain changed during test run; repeat")
    atomic_json(scenario_path(domain_id).with_name("test-results.json"), result)
    return result
