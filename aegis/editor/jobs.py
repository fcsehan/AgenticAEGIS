"""Cancelable inference jobs. Cancellation prevents adoption, not server-side compute."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aegis.audit.trail import AuditTrail
from aegis.editor.api import GenerateRequest, RefineRequest, generate_rules, refine_rule
from aegis.editor.mediation import authorize_editor

router = APIRouter(prefix="/api", dependencies=[Depends(authorize_editor)])


@dataclass
class InferenceJob:
    id: str
    domain_id: str
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    result: dict[str, Any] | None = None
    error: str = ""
    progress: str = ""
    task: asyncio.Task[None] | None = field(default=None, repr=False)

    def response(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domainId": self.domain_id,
            "status": self.status,
            "createdAt": self.created_at,
            "result": self.result,
            "error": self.error,
            "progress": self.progress,
        }


class JobTracker:
    def __init__(self) -> None:
        self.jobs: dict[str, InferenceJob] = {}
        self.audit: AuditTrail | None = None

    def start(self, domain_id: str, work: Callable[[], Awaitable[dict[str, Any]]]) -> InferenceJob:
        if sum(j.status in {"queued", "running"} for j in self.jobs.values()) >= 2:
            raise HTTPException(429, "Two inference jobs are already running")
        job = InferenceJob(uuid.uuid4().hex, domain_id)
        # Bound memory: completed results are session artifacts, not normative sources.
        if len(self.jobs) >= 100:
            for key, previous in list(self.jobs.items()):
                if previous.status not in {"queued", "running"}:
                    del self.jobs[key]
                    break
        self.jobs[job.id] = job

        async def run() -> None:
            job.status = "running"
            try:
                result = await work()
                if job.status != "cancelled":
                    if self.audit:
                        self.audit.log_event(
                            "EDITOR_INFERENCE_COMPLETE",
                            {
                                "jobId": job.id,
                                "domainId": job.domain_id,
                                "revision": result.get("revision"),
                                "inference": result.get("inference"),
                                "sourceHash": result.get("sourceHash"),
                            },
                        )
                    job.result = result
                    job.status = "succeeded"
            except asyncio.CancelledError:
                job.status = "cancelled"
                job.result = None
            except HTTPException as exc:
                job.status = "failed"
                job.error = str(exc.detail)
            except Exception:
                job.status = "failed"
                job.error = "Inference failed (connection, timeout or invalid model response)"

        job.task = asyncio.create_task(run())
        return job

    def cancel(self, job_id: str) -> InferenceJob:
        job = self.get(job_id)
        if job.status in {"queued", "running"}:
            if self.audit:
                self.audit.log_event("EDITOR_JOB_CANCEL", {"jobId": job.id})
            job.status = "cancelled"
            job.result = None
            if job.task:
                job.task.cancel()
        return job

    def get(self, job_id: str) -> InferenceJob:
        if job_id not in self.jobs:
            raise HTTPException(404, "Job not found; a backend restart discards unfinished jobs")
        return self.jobs[job_id]


def tracker(request: Request) -> JobTracker:
    value: JobTracker = request.app.state.jobs
    return value


@router.post("/domains/{domain_id}/jobs/generate", status_code=202)
async def generate_job(domain_id: str, body: GenerateRequest, request: Request) -> dict[str, Any]:
    return (
        tracker(request)
        .start(domain_id, lambda: generate_rules(domain_id, body, request))
        .response()
    )


@router.post("/domains/{domain_id}/jobs/refine", status_code=202)
async def refine_job(domain_id: str, body: RefineRequest, request: Request) -> dict[str, Any]:
    return (
        tracker(request).start(domain_id, lambda: refine_rule(domain_id, body, request)).response()
    )


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    return tracker(request).get(job_id).response()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    return tracker(request).cancel(job_id).response()
