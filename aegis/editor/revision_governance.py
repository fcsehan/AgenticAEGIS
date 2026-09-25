"""Local snapshot governance. No git checkout/add/revert in a user's workspace."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aegis.editor.api import CheckRequest, get_state
from aegis.editor.domain_analysis import analyze_domain
from aegis.editor.mediation import authorize_editor, enforce
from aegis.editor.scenario_api import ScenarioSet, atomic_json, evaluate_plan, get_scenarios
from aegis.editor.source_store import read_sources, source_revision
from aegis.guard.action import Action
from aegis.guard.guard import Guard

router = APIRouter(prefix="/api/domains", dependencies=[Depends(authorize_editor)])


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def metadata_path(domain_id: str) -> Path:
    source = get_state().sources.get(domain_id)
    if source is None:
        raise HTTPException(404, "Source domain not found")
    source.load()
    return source.directory / "governance.json"


def read_metadata(domain_id: str) -> dict[str, Any]:
    path = metadata_path(domain_id)
    if path.is_symlink():
        raise HTTPException(409, "Governance symlinks are not supported")
    if path.exists():
        value: dict[str, Any] = json.loads(path.read_text())
        return value
    return {"versions": [], "review": None, "activeVersion": None}


def evidence(domain_id: str) -> dict[str, Any]:
    state = get_state()
    source = state.sources[domain_id]
    sources, revision = source.load()
    scenarios = get_scenarios(domain_id)
    result_path = source.directory / "test-results.json"
    results = json.loads(result_path.read_text()) if result_path.exists() else {}
    analysis = analyze_domain(state.domains[domain_id], state.guards[domain_id])
    checks = {
        "sourceDiagnostics": analysis["valid"],
        "notArchived": state.domains[domain_id].status != "Archived",
        "compiled": domain_id in state.guards and state.domains[domain_id].revision == revision,
        "tests": bool(results.get("passed"))
        and results.get("revision") == revision
        and results.get("scenarioHash") == digest(scenarios),
        "positiveAndNegativeCases": {s["expected"] for s in scenarios["scenarios"]}
        >= {"PERMITTED", "FORBIDDEN"},
    }
    document = (
        f"# Domain {domain_id}\n\nRevision: {revision}\n\n"
        "Local operator review. Test coverage is scoped to the declared scenarios.\n"
        "No claim of completeness of natural-language interpretation.\n\n"
        + "\n".join(f"## {name}\n\n```lisp\n{content}\n```" for name, content in sources.items())
    )
    return {
        "revision": revision,
        "checks": checks,
        "scenarioHash": digest(scenarios),
        "testHash": digest(results),
        "documentHash": digest(document),
        "document": document,
    }


class ReviewRequest(BaseModel):
    revision: str
    message: str = Field(min_length=5, max_length=2000)
    acknowledge_limits: bool = Field(alias="acknowledgeLimits")


class PublishRequest(BaseModel):
    revision: str
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    message: str = Field(min_length=1, max_length=2000)


class ActivationRequest(BaseModel):
    version: str


@router.get("/{domain_id}/governance")
def governance(domain_id: str) -> dict[str, Any]:
    meta = read_metadata(domain_id)
    current = evidence(domain_id)
    review = meta.get("review")
    reviewed = bool(
        review
        and all(
            review.get(k) == current[k]
            for k in ("revision", "scenarioHash", "testHash", "documentHash")
        )
    )
    return {
        **meta,
        "evidence": current,
        "reviewCurrent": reviewed,
        "canPublish": reviewed and all(current["checks"].values()),
    }


@router.post("/{domain_id}/governance/review")
def review(domain_id: str, body: ReviewRequest, request: Request) -> dict[str, Any]:
    meta = read_metadata(domain_id)
    current = evidence(domain_id)
    if (
        body.revision != current["revision"]
        or not body.acknowledge_limits
        or not all(current["checks"].values())
    ):
        raise HTTPException(
            409,
            "Review needs current compilation, passing positive/negative tests and acknowledgment",
        )
    record = {k: current[k] for k in ("revision", "scenarioHash", "testHash", "documentHash")}
    record.update(
        {
            "actor": "localOperator",
            "message": body.message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    request.app.state.editor_audit.log_event("EDITOR_REVIEW", {"domain": domain_id, **record})
    meta["review"] = record
    atomic_json(metadata_path(domain_id), meta)
    get_state().domains[domain_id].status = "Review"
    return governance(domain_id)


@router.post("/{domain_id}/governance/publish")
def publish(domain_id: str, body: PublishRequest, request: Request) -> dict[str, Any]:
    status = governance(domain_id)
    if not status["canPublish"] or body.revision != status["evidence"]["revision"]:
        raise HTTPException(409, "Review or test evidence is missing or stale")
    enforce(request, "releaseEditor", {"evidence": "reviewedSnapshot"})
    meta = read_metadata(domain_id)
    existing = next((v for v in meta["versions"] if v["version"] == body.version), None)
    if existing:
        if existing["revision"] == body.revision:
            return governance(domain_id)
        raise HTTPException(409, "Version already refers to different content")
    source = get_state().sources[domain_id]
    sources, revision = source.load()
    source.save(sources, revision)  # Ensure an immutable snapshot even for an unedited import.
    entry = {
        "version": body.version,
        "revision": revision,
        "message": body.message,
        "actor": "localOperator",
        "timestamp": datetime.now(UTC).isoformat(),
        "review": meta["review"],
        "scenarios": get_scenarios(domain_id),
        "document": status["evidence"]["document"],
    }
    request.app.state.editor_audit.log_event(
        "EDITOR_PUBLISH", {"domain": domain_id, "version": body.version, "revision": revision}
    )
    meta["versions"].append(entry)
    atomic_json(metadata_path(domain_id), meta)
    get_state().domains[domain_id].status = "Published"
    return governance(domain_id)


def released_guard(domain_id: str, version: str) -> tuple[Guard, dict[str, Any]]:
    meta = read_metadata(domain_id)
    entry = next((v for v in meta["versions"] if v["version"] == version), None)
    if entry is None:
        raise HTTPException(404, "Published version not found")
    source = get_state().sources[domain_id]
    revision = entry["revision"]
    if (
        not isinstance(revision, str)
        or len(revision) != 64
        or any(c not in "0123456789abcdef" for c in revision)
    ):
        raise HTTPException(409, "Invalid release revision")
    paths = sorted((source.directory / revision).glob("*.meld"))
    if any(not p.resolve().is_relative_to(source.directory.resolve()) for p in paths):
        raise HTTPException(409, "Release source escapes storage")
    if source_revision(read_sources(paths)) != revision:
        raise HTTPException(409, "Released snapshot integrity check failed")
    return Guard.from_meld_files(paths), entry


@router.post("/{domain_id}/governance/activate")
def activate(domain_id: str, body: ActivationRequest, request: Request) -> dict[str, Any]:
    guard, entry = released_guard(domain_id, body.version)
    # Re-evaluate saved action scenarios under the current engine before activation.
    scenarios = ScenarioSet.model_validate(entry["scenarios"])
    for scenario in scenarios.scenarios:
        if scenario.action is not None:
            action = scenario.action
            result = guard.check(
                Action(
                    action_type=action.action_type,
                    agent_id=action.agent,
                    proposition=action.parameters,
                    context=action.context,
                )
            )
            decision = result.decision.value
        elif scenario.plan is not None:
            decision = evaluate_plan(
                domain_id, scenario.plan, guard=guard, revision=entry["revision"]
            )["decision"]
        else:
            raise HTTPException(409, "Invalid release scenario")
        if decision != scenario.expected:
            raise HTTPException(409, "Release regression failed under the current engine")
    enforce(request, "releaseEditor", {"evidence": "reviewedSnapshot"})
    meta = read_metadata(domain_id)
    request.app.state.editor_audit.log_event(
        "EDITOR_ACTIVATE",
        {
            "domain": domain_id,
            "fromVersion": meta["activeVersion"],
            "toVersion": body.version,
            "revision": entry["revision"],
            "target": "editor-runtime",
        },
    )
    meta["activeVersion"] = body.version
    atomic_json(metadata_path(domain_id), meta)
    return governance(domain_id)


@router.post("/{domain_id}/runtime/check")
def runtime_check(domain_id: str, body: CheckRequest) -> dict[str, Any]:
    version = read_metadata(domain_id)["activeVersion"]
    if not version:
        raise HTTPException(409, "No active released guard")
    guard, entry = released_guard(domain_id, version)
    verdict = guard.check(
        Action(
            action_type=body.action_type,
            agent_id=body.agent,
            proposition=body.parameters,
            context=body.context,
        )
    )
    return {
        "version": version,
        "revision": entry["revision"],
        "decision": verdict.decision.value,
        "reasonType": verdict.reason_type.value,
        "justificationChain": list(verdict.justification_chain),
    }
