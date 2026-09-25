"""AEGIS-1001 / 1801 / 1806: REST API (FastAPI).

Provides HTTP endpoints for the Guard service:
- POST /v1/check — Action → Verdict
- GET  /v1/health — health check with KB status
- GET  /v1/stats — guard statistics
- POST /v1/audit/verify — hash-chain verification
- GET  /v1/tool-schema — LLM tool-use schema
- POST /v1/broker/read — Guarded file read (AEGIS-1801)
- POST /v1/broker/search — Guarded file search (AEGIS-1801)
- POST /v1/output/check — OutputFilter text check (AEGIS-1806)
- POST /v1/taint/ingest — Ingest taint markers (AEGIS-1806)

All responses include X-Guard-Duration-Ms and X-Request-Id headers.
Error responses follow RFC 7807 (Problem Details).
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aegis.api.tool_schema import generate_tool_schema
from aegis.audit.integrity import verify_integrity
from aegis.audit.trail import AuditTrail
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision
from aegis.hardening.output_guard import OutputFilter
from aegis.hardening.taint import TaintLevel, TaintTracker
from aegis.ifc.broker import RetrievalBroker

# ── Pydantic models ──────────────────────────────────────────────


class ActionRequest(BaseModel):
    """Request body for POST /v1/check."""

    action_type: str
    agent_id: str
    proposition: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class VerdictResponse(BaseModel):
    """Response body for POST /v1/check."""

    decision: str
    reason_type: str
    justification_chain: list[str]
    norms_applied: list[str]
    action_type: str
    agent_id: str
    explanation: str


class PlanStepRequest(BaseModel):
    """One step in a plan-check request body (AEGIS-2719)."""

    action_type: str
    agent_id: str
    proposition: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    step_id: str = ""
    scheduled_duration_s: float = 0.0
    pre_state: dict[str, Any] = Field(default_factory=dict)
    post_state: dict[str, Any] = Field(default_factory=dict)


class PlanCheckRequest(BaseModel):
    """Request body for POST /v1/plan_check (AEGIS-2719)."""

    plan_id: str = ""
    initial_state: dict[str, Any] = Field(default_factory=dict)
    steps: list[PlanStepRequest] = Field(default_factory=list)


class PlanViolationDTO(BaseModel):
    """One plan-level violation in the response."""

    violation_type: str
    step_index: int
    constraint_id: str
    detail: str


class PlanStepVerdictDTO(BaseModel):
    """Per-step verdict in the plan-check response."""

    decision: str
    reason_type: str
    action_type: str
    agent_id: str


class PlanVerdictResponse(BaseModel):
    """Response body for POST /v1/plan_check (AEGIS-2719)."""

    plan_decision: str
    reason_summary: str
    evaluation_mode: str
    per_step_verdicts: list[PlanStepVerdictDTO]
    violations: list[PlanViolationDTO]


class HealthResponse(BaseModel):
    """Response body for GET /v1/health."""

    status: str
    kb_fact_count: int
    microtheories: list[str]
    norm_count: int
    action_types: list[str]
    audit_trail_active: bool


class StatsResponse(BaseModel):
    """Response body for GET /v1/stats."""

    total_checks: int
    permitted: int
    forbidden: int
    undecidable: int


class AuditVerifyRequest(BaseModel):
    """Request body for POST /v1/audit/verify."""

    path: str | None = None


class AuditVerifyResponse(BaseModel):
    """Response body for POST /v1/audit/verify."""

    valid: bool
    total_entries: int
    first_entry_id: int | None
    last_entry_id: int | None
    errors: list[dict[str, Any]]
    verification_time_ms: float


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details response."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str = ""


# ── AEGIS-1801: Broker request/response models ──────────────────


class BrokerReadRequest(BaseModel):
    """Request body for POST /v1/broker/read."""

    path: str
    classification: str
    agent_id: str
    purpose: str = "internalAnalysis"
    canary_tokens: list[str] = Field(default_factory=list)


class BrokerReadResponse(BaseModel):
    """Response body for POST /v1/broker/read."""

    content: str
    response_mode: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    redacted: bool


class BrokerSearchRequest(BaseModel):
    """Request body for POST /v1/broker/search."""

    query: str
    files: list[dict[str, str]] = Field(default_factory=list)
    agent_id: str
    purpose: str = "internalAnalysis"


class BrokerSearchResponse(BaseModel):
    """Response body for POST /v1/broker/search."""

    matches: list[dict[str, Any]] = Field(default_factory=list)
    response_mode: str
    redacted: bool
    excluded_files: list[str] = Field(default_factory=list)


# ── AEGIS-1806: OutputFilter request/response models ─────────────


class OutputCheckRequest(BaseModel):
    """Request body for POST /v1/output/check."""

    text: str
    taint_state: dict[str, Any] | None = None
    recipient: str = "user"
    purpose: str = "response"


class OutputCheckResponse(BaseModel):
    """Response body for POST /v1/output/check."""

    safe: bool
    redacted_text: str
    violations: list[str] = Field(default_factory=list)
    blocked_markers: list[str] = Field(default_factory=list)


class TaintIngestRequest(BaseModel):
    """Request body for POST /v1/taint/ingest."""

    markers: list[dict[str, str]]


class TaintIngestResponse(BaseModel):
    """Response body for POST /v1/taint/ingest."""

    ingested: int
    is_tainted: bool


# ── Guard State ──────────────────────────────────────────────────


class GuardState:
    """Holds the Guard instance and runtime statistics."""

    def __init__(
        self,
        guard: Guard,
        audit_trail: AuditTrail | None = None,
        audit_path: Path | None = None,
        broker: RetrievalBroker | None = None,
        output_guard: OutputFilter | None = None,
        taint_tracker: TaintTracker | None = None,
    ) -> None:
        self.guard = guard
        self.audit_trail = audit_trail
        self.audit_path = audit_path
        self.broker = broker
        self.output_guard = output_guard or OutputFilter()
        self.taint_tracker = taint_tracker or TaintTracker()
        self.total_checks = 0
        self.permitted = 0
        self.forbidden = 0
        self.undecidable = 0


# ── App factory ──────────────────────────────────────────────────


def create_app(state: GuardState) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="AEGIS Guard API",
        version="1.0.0",
        description="Ethical action guard for LLM agents",
    )

    # Store state on app for access in routes
    app.state.guard_state = state

    # ── Middleware: request ID + timing ────────────────────────

    @app.middleware("http")
    async def add_headers(request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Guard-Duration-Ms"] = f"{duration_ms:.2f}"
        return response

    # ── Routes ────────────────────────────────────────────────

    @app.post("/v1/check", response_model=VerdictResponse)
    async def check_action(body: ActionRequest) -> VerdictResponse:
        gs: GuardState = app.state.guard_state

        action = Action(
            action_type=body.action_type,
            agent_id=body.agent_id,
            proposition=body.proposition,
            context=body.context,
        )

        verdict = gs.guard.check(action)

        gs.total_checks += 1
        if verdict.decision == Decision.PERMITTED:
            gs.permitted += 1
        elif verdict.decision == Decision.FORBIDDEN:
            gs.forbidden += 1
        else:
            gs.undecidable += 1

        return VerdictResponse(
            decision=verdict.decision.value,
            reason_type=verdict.reason_type.value,
            justification_chain=list(verdict.justification_chain),
            norms_applied=list(verdict.norms_applied),
            action_type=verdict.action_type,
            agent_id=verdict.agent_id,
            explanation=verdict.explain(),
        )

    @app.post("/v1/plan_check", response_model=PlanVerdictResponse)
    async def check_plan(body: PlanCheckRequest) -> PlanVerdictResponse:
        """AEGIS-2719 (Epic 27) — evaluate a plan via Guard.plan_check.

        Plan-orientated callers (HTN planners, BPMN engines, OpenCode-
        like tool-call sequencers) submit a Plan and receive a
        ``PlanVerdict`` with per-step decisions and plan-level
        violation list. Exit policy: PERMITTED → caller may execute
        the plan in order; FORBIDDEN/UNDECIDABLE → caller must not.
        """
        from aegis.guard.plan import Plan, PlanStep, StateSnapshot

        gs: GuardState = app.state.guard_state

        steps: list[PlanStep] = []
        for raw in body.steps:
            steps.append(PlanStep(
                action=Action(
                    action_type=raw.action_type,
                    agent_id=raw.agent_id,
                    proposition=raw.proposition,
                    context=raw.context,
                ),
                step_id=raw.step_id,
                scheduled_duration_s=raw.scheduled_duration_s,
                pre_state=StateSnapshot(fields=raw.pre_state),
                post_state=StateSnapshot(fields=raw.post_state),
            ))
        plan = Plan(
            steps=tuple(steps),
            initial_state=StateSnapshot(fields=body.initial_state),
            plan_id=body.plan_id,
        )

        verdict = gs.guard.plan_check(plan)

        return PlanVerdictResponse(
            plan_decision=verdict.plan_decision.value,
            reason_summary=verdict.reason_summary,
            evaluation_mode=verdict.evaluation_mode,
            per_step_verdicts=[
                PlanStepVerdictDTO(
                    decision=sv.decision.value,
                    reason_type=sv.reason_type.value,
                    action_type=sv.action_type,
                    agent_id=sv.agent_id,
                )
                for sv in verdict.per_step_verdicts
            ],
            violations=[
                PlanViolationDTO(
                    violation_type=v.violation_type.value,
                    step_index=v.step_index,
                    constraint_id=v.constraint_id,
                    detail=v.detail,
                )
                for v in verdict.violations
            ],
        )

    @app.get("/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        gs: GuardState = app.state.guard_state
        guard = gs.guard
        return HealthResponse(
            status="ok",
            kb_fact_count=guard._kb.fact_count,
            microtheories=list(guard._kb.microtheories),
            norm_count=len(guard._norms),
            action_types=guard._registry.action_types,
            audit_trail_active=gs.audit_trail is not None,
        )

    @app.get("/v1/stats", response_model=StatsResponse)
    async def stats() -> StatsResponse:
        gs: GuardState = app.state.guard_state
        return StatsResponse(
            total_checks=gs.total_checks,
            permitted=gs.permitted,
            forbidden=gs.forbidden,
            undecidable=gs.undecidable,
        )

    @app.post("/v1/audit/verify", response_model=AuditVerifyResponse)
    async def audit_verify(
        body: AuditVerifyRequest,
    ) -> AuditVerifyResponse | JSONResponse:
        gs: GuardState = app.state.guard_state
        path = Path(body.path) if body.path else gs.audit_path

        if path is None:
            return JSONResponse(
                status_code=400,
                content=ProblemDetail(
                    title="Bad Request",
                    status=400,
                    detail="No audit path configured or provided",
                ).model_dump(),
            )

        result = verify_integrity(path)
        return AuditVerifyResponse(
            valid=result.valid,
            total_entries=result.total_entries,
            first_entry_id=result.first_entry_id,
            last_entry_id=result.last_entry_id,
            errors=[
                {
                    "entry_id": e.entry_id,
                    "error_type": e.error_type,
                    "message": e.message,
                }
                for e in result.errors
            ],
            verification_time_ms=result.verification_time_ms,
        )

    @app.get("/v1/tool-schema")
    async def tool_schema() -> dict[str, Any]:
        gs: GuardState = app.state.guard_state
        return generate_tool_schema(gs.guard._registry)

    # ── AEGIS-1801: Broker endpoints ──────────────────────────

    @app.post("/v1/broker/read", response_model=BrokerReadResponse)
    async def broker_read(body: BrokerReadRequest) -> BrokerReadResponse | JSONResponse:
        gs: GuardState = app.state.guard_state

        # Delegate to Guard via readDocument action
        action = Action(
            action_type="readDocument",
            agent_id=body.agent_id,
            proposition={
                "sourceClassification": body.classification.lower(),
                "purpose": body.purpose,
            },
        )
        verdict = gs.guard.check(action)

        if verdict.decision == Decision.FORBIDDEN:
            return BrokerReadResponse(
                content="",
                response_mode="deny",
                provenance={
                    "source_path": body.path,
                    "classification": body.classification,
                },
                redacted=True,
            )

        if verdict.decision == Decision.UNDECIDABLE:
            return BrokerReadResponse(
                content="",
                response_mode="metadata-only",
                provenance={
                    "source_path": body.path,
                    "classification": body.classification,
                },
                redacted=True,
            )

        # PERMITTED — in sidecar mode we return the verdict; the host
        # reads the file locally.  For proxy-read mode, the host would
        # send the content through this endpoint.
        return BrokerReadResponse(
            content="",
            response_mode="full-content",
            provenance={
                "source_path": body.path,
                "classification": body.classification,
            },
            redacted=False,
        )

    @app.post("/v1/broker/search", response_model=BrokerSearchResponse)
    async def broker_search(
        body: BrokerSearchRequest,
    ) -> BrokerSearchResponse:
        gs: GuardState = app.state.guard_state

        excluded: list[str] = []
        allowed: list[dict[str, str]] = []

        for file_entry in body.files:
            classification = file_entry.get("classification", "public").lower()
            file_path = file_entry.get("path", "")

            action = Action(
                action_type="readDocument",
                agent_id=body.agent_id,
                proposition={
                    "sourceClassification": classification,
                    "purpose": body.purpose,
                },
            )
            verdict = gs.guard.check(action)

            if verdict.decision == Decision.PERMITTED:
                allowed.append(file_entry)
            else:
                excluded.append(file_path)

        return BrokerSearchResponse(
            matches=[],
            response_mode="full-content" if not excluded else "redacted-snippet",
            redacted=bool(excluded),
            excluded_files=excluded,
        )

    # ── AEGIS-1806: OutputFilter + Taint endpoints ─────────────

    @app.post("/v1/output/check", response_model=OutputCheckResponse)
    async def output_check(body: OutputCheckRequest) -> OutputCheckResponse:
        gs: GuardState = app.state.guard_state

        if body.taint_state:
            # Reconstruct taint markers from provided state
            _ingest_taint_markers(
                gs.taint_tracker,
                body.taint_state.get("markers", []),
            )
            result = gs.output_guard.check_with_taint(
                body.text,
                gs.taint_tracker,
                recipient=body.recipient,
                purpose=body.purpose,
            )
        else:
            result = gs.output_guard.check(body.text)

        return OutputCheckResponse(
            safe=result.safe,
            redacted_text=result.redacted_text,
            violations=list(result.violations),
            blocked_markers=list(result.blocked_markers),
        )

    @app.post("/v1/taint/ingest", response_model=TaintIngestResponse)
    async def taint_ingest(body: TaintIngestRequest) -> TaintIngestResponse:
        gs: GuardState = app.state.guard_state
        count = _ingest_taint_markers(gs.taint_tracker, body.markers)
        return TaintIngestResponse(
            ingested=count,
            is_tainted=gs.taint_tracker.is_tainted(),
        )

    return app


# ── Helpers ──────────────────────────────────────────────────────

_LEVEL_MAP: dict[str, TaintLevel] = {
    "PUBLIC": TaintLevel.PUBLIC,
    "INTERNAL": TaintLevel.INTERNAL,
    "CONFIDENTIAL": TaintLevel.CONFIDENTIAL,
    "SECRET": TaintLevel.SECRET,
}


def _ingest_taint_markers(
    tracker: TaintTracker,
    markers: list[dict[str, str]],
) -> int:
    """Ingest taint markers from a list of dicts into a TaintTracker."""
    count = 0
    for entry in markers:
        value = entry.get("value", "")
        source = entry.get("source", "sidecar")
        level_str = entry.get("level", "SECRET").upper()
        level = _LEVEL_MAP.get(level_str, TaintLevel.SECRET)
        if value:
            tracker.mark([value], source=source, level=level)
            count += 1
    return count
