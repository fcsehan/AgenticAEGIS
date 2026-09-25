"""Document-to-draft workflow using the existing DIP, isolated from active domains."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from aegis.dip.coexistence import validate_output_target
from aegis.dip.pipeline import run_pipeline
from aegis.editor.api import get_state
from aegis.editor.jobs import tracker
from aegis.editor.mediation import authorize_editor
from aegis.editor.provider_api import configured_client, store
from aegis.guard.guard import Guard

router = APIRouter(prefix="/api/dip", dependencies=[Depends(authorize_editor)])


class DocumentRequest(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=500_000)
    source_type: Literal["text", "html"] = Field(default="text", alias="sourceType")
    language: Literal["en", "auto"] = "en"
    provider_id: str = Field(alias="providerId")
    model_id: str = Field(alias="modelId")


@router.post("/jobs", status_code=202)
async def start_dip(body: DocumentRequest, request: Request) -> dict[str, Any]:
    state = get_state()
    project = state.project_path
    if project is None:
        raise HTTPException(409, "Open a project first")
    client = configured_client(request, body.provider_id, body.model_id)
    if (
        store(request).load().revision,
        body.provider_id,
        client.model_id,
    ) not in request.app.state.capabilities:
        raise HTTPException(409, "Verify model tool capability before document extraction")

    inference = {
        "providerId": client.provider_id,
        "modelId": client.model_id,
        "profileRevision": store(request).load().revision,
        "temperature": client._temperature,
        "maxTokens": client._max_tokens,
        "timeout": client._timeout,
        "classification": "confidentialData",
    }

    def execute() -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="aegis-dip-") as temp:
            directory = Path(temp)
            source = directory / ("source.html" if body.source_type == "html" else "source.txt")
            source.write_text(body.content, encoding="utf-8")

            def progress(stage: int, message: str) -> None:
                if job.status == "cancelled":
                    raise ValueError("Document job cancelled")
                job.progress = f"{stage}/6: {message}"

            output = directory / "generated"
            result = run_pipeline(
                str(source),
                body.name,
                client,
                output,
                source_type=body.source_type,
                language=body.language,
                verify=True,
                on_progress=progress,
            )
            paths = sorted(output.rglob("*.meld"))
            if not paths:
                raise ValueError("DIP generated no MELD files")
            Guard.from_meld_files(paths)
            reports = {
                p.name: p.read_text() for p in output.rglob("*") if p.suffix in {".md", ".json"}
            }
            return {
                "inference": inference,
                "name": body.name,
                "title": body.title,
                "language": body.language,
                "sourceType": body.source_type,
                "project": str(project),
                "sourceHash": hashlib.sha256(body.content.encode()).hexdigest(),
                "files": {p.name: p.read_text() for p in paths},
                "reports": reports,
                "summary": result.summary(),
                "status": "Draft",
            }

    async def work() -> dict[str, Any]:
        return await run_in_threadpool(execute)

    job = tracker(request).start(f"dip-{body.name}", work)
    return job.response()


@router.post("/jobs/{job_id}/adopt")
def adopt_dip(job_id: str, request: Request) -> dict[str, Any]:
    job = tracker(request).get(job_id)
    result = job.result
    if job.status != "succeeded" or result is None or not job.domain_id.startswith("dip-"):
        raise HTTPException(409, "A completed document job is required")
    project = get_state().project_path
    if project is None or str(project) != result["project"]:
        raise HTTPException(409, "Open the original project before adoption")
    target = project / f"generated-{result['name']}"
    if target.exists():
        raise HTTPException(
            409, "Generated domain already exists; no existing domain is overwritten"
        )
    validate_output_target(target, result["name"])
    stage_root = project / ".aegis-editor"
    if not stage_root.resolve().is_relative_to(project):
        raise HTTPException(409, "Draft staging escapes project")
    stage_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=stage_root) as temporary:
        stage = Path(temporary)
        for name, content in {**result["files"], **result["reports"]}.items():
            if Path(name).name != name:
                raise HTTPException(409, "Invalid generated filename")
            (stage / name).write_text(content, encoding="utf-8")
        from aegis.editor.scenario_api import atomic_json

        atomic_json(
            stage / ".aegis-editor" / "dip-origin.json",
            {
                key: result[key]
                for key in ("title", "sourceHash", "language", "sourceType", "inference", "reports")
            },
        )
        request.app.state.editor_audit.log_event(
            "EDITOR_DIP_ADOPT",
            {"domain": target.name, "sourceHash": result["sourceHash"], "jobId": job.id},
        )
        os.rename(stage, target)
    return get_state().load_project(project)
