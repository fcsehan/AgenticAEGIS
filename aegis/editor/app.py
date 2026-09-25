"""Local editor application with independent state and a same-origin write boundary.

Run with ``aegis-editor --workspace /path/to/projects``. One worker only.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from aegis.audit.trail import AuditTrail
from aegis.editor.api import EditorState, request_state, router
from aegis.editor.dip_api import router as dip_router
from aegis.editor.edit_api import router as edit_router
from aegis.editor.jobs import JobTracker
from aegis.editor.jobs import router as job_router
from aegis.editor.plan_edit_api import router as plan_edit_router
from aegis.editor.project_api import router as project_router
from aegis.editor.provider_api import router as provider_router
from aegis.editor.provider_config import ProviderStore
from aegis.editor.revision_governance import router as revision_router
from aegis.editor.scenario_api import router as scenario_router
from aegis.editor.structure_api import router as structure_router
from aegis.guard.guard import Guard


def create_editor_app(
    workspace: Path,
    config_dir: Path | None = None,
    policy_dir: Path | None = None,
) -> FastAPI:
    workspace = workspace.resolve(strict=True)
    app = FastAPI(title="AEGIS Domain Editor", version="0.1.0")
    app.state.editor_state = EditorState()
    app.state.workspace = workspace
    app.state.capabilities = set()
    app.state.jobs = JobTracker()
    mutation_lock = asyncio.Lock()
    app.state.provider_store = ProviderStore(
        config_dir
        or Path(
            os.environ.get("AEGIS_EDITOR_CONFIG_DIR", str(Path.home() / ".config/aegis/editor"))
        )
    )
    app.state.provider_store.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    app.state.editor_guard = Guard.from_meld_files(
        sorted((policy_dir or Path(__file__).parent / "policy").glob("*.meld"))
    )
    policy_files = sorted((policy_dir or Path(__file__).parent / "policy").glob("*.meld"))
    app.state.editor_policy_revision = hashlib.sha256(
        b"".join(p.read_bytes() for p in policy_files)
    ).hexdigest()
    app.state.editor_audit = AuditTrail(app.state.provider_store.path.parent / "editor-audit.jsonl")
    app.state.jobs.audit = app.state.editor_audit
    session_path = app.state.provider_store.path.parent / "session.json"
    if session_path.exists():
        try:
            previous = Path(json.loads(session_path.read_text())["project"]).resolve()
            if previous.is_relative_to(workspace):
                app.state.editor_state.load_project(previous)
        except (OSError, ValueError, KeyError):
            # Startup remains available for recovery via a new explicit project open.
            pass
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic's default response repeats input values, including mistaken API keys.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": error["loc"], "type": error["type"], "msg": error["msg"]}
                    for error in exc.errors()
                ]
            },
        )

    @app.middleware("http")
    async def boundary(request: Request, call_next: Any) -> Any:
        if request.client and request.client.host != "testclient":
            try:
                local_peer = ipaddress.ip_address(request.client.host).is_loopback
            except ValueError:
                local_peer = False
            if not local_peer:
                return JSONResponse(
                    {"detail": "Editor supports local loopback clients only"}, status_code=403
                )
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and (
                urlsplit(origin).netloc != request.headers.get("host")
                or urlsplit(origin).scheme != request.url.scheme
            ):
                return JSONResponse(
                    {"detail": "Cross-origin editor access denied"}, status_code=403
                )
            if (
                request.method not in {"GET", "HEAD", "OPTIONS"}
                and request.headers.get("x-aegis-editor") != "1"
            ):
                return JSONResponse({"detail": "Editor request header required"}, status_code=403)
        token = request_state.set(app.state.editor_state)
        try:
            # Serialize project reads/writes against revision-changing operations.
            # Long inference runs release the gate and must validate their context afterwards.
            is_inference = any(
                request.url.path.endswith(suffix)
                for suffix in (
                    "/generate",
                    "/generate/refine",
                    "/capability",
                    "/probe",
                    "/providers/refresh",
                )
            )
            if request.url.path.startswith("/api/") and not is_inference:
                async with mutation_lock:
                    return await call_next(request)
            return await call_next(request)
        finally:
            request_state.reset(token)

    app.include_router(project_router)
    app.include_router(plan_edit_router)
    app.include_router(structure_router)
    app.include_router(edit_router)
    app.include_router(dip_router)
    app.include_router(job_router)
    app.include_router(revision_router)
    app.include_router(scenario_router)
    app.include_router(provider_router)
    app.include_router(router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ready",
            "version": "0.1.0",
            "mode": "local-development",
        }

    dist = Path(__file__).parent / "frontend" / "dist"

    @app.get("/{asset_path:path}")
    def frontend(asset_path: str) -> Any:
        if asset_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        target = (dist / asset_path).resolve()
        if not target.is_relative_to(dist.resolve()):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        if target.is_file():
            return FileResponse(target)
        if Path(asset_path).suffix:
            return JSONResponse({"detail": "Asset not found"}, status_code=404)
        if (dist / "index.html").is_file():
            return FileResponse(dist / "index.html")
        return JSONResponse({"detail": "Build frontend first: npm run build"}, status_code=503)

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="AEGIS local domain editor")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path)
    parser.add_argument("--policy-dir", type=Path)
    transfer = parser.add_mutually_exclusive_group()
    transfer.add_argument("--backup", type=Path)
    transfer.add_argument("--restore", type=Path)
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    if args.backup or args.restore:
        from aegis.editor.backup import backup_project, restore_project

        config = args.config_dir or Path(
            os.environ.get("AEGIS_EDITOR_CONFIG_DIR", str(Path.home() / ".config/aegis/editor"))
        )
        if args.backup:
            backup_project(args.workspace, config, args.backup)
            print(f"Backup written: {args.backup}")
        else:
            restore_project(args.restore, args.workspace, config)
            print(f"Project restored: {args.workspace}")
        return
    uvicorn.run(
        create_editor_app(args.workspace, args.config_dir, args.policy_dir),
        host="127.0.0.1",
        proxy_headers=False,
        port=args.port,
    )


if __name__ == "__main__":
    main()
