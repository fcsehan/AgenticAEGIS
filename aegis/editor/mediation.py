"""Formal local-editor mediation; deliberately no network-user identity claims."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import unquote, urlsplit

from fastapi import HTTPException, Request

from aegis.audit.trail import AuditTrail
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision


def enforce(
    request: Request,
    action_type: str,
    parameters: dict[str, str] | None = None,
    audit_context: dict[str, str] | None = None,
) -> None:
    guard: Guard | None = getattr(request.app.state, "editor_guard", None)
    if guard is None:
        # Bare legacy router is used by existing library tests only.
        if getattr(request.app.state, "editor_state", None) is not None:
            raise HTTPException(503, "Editor mediation is unavailable")
        return
    action = Action(
        action_type=action_type,
        agent_id="localOperator",
        proposition=parameters or {},
        context={
            "editorRoute": request.url.path[:256],
            "policyRevision": getattr(request.app.state, "editor_policy_revision", ""),
            **(audit_context or {}),
        },
    )
    verdict = guard.check(action)
    audit: AuditTrail = request.app.state.editor_audit
    try:
        audit.log(action, verdict)
    except Exception as exc:
        raise HTTPException(503, "Editor audit unavailable; operation blocked") from exc
    if verdict.decision is not Decision.PERMITTED:
        raise HTTPException(403, f"Editor policy: {verdict.decision.value}")


def require_project_context(request: Request) -> None:
    state = getattr(request.app.state, "editor_state", None)
    scoped = request.url.path.startswith(("/api/domains", "/api/dip/", "/api/project/import"))
    if (
        state is not None
        and state.project_path is not None
        and scoped
        and unquote(request.headers.get("x-aegis-project", "")) != str(state.project_path)
    ):
        raise HTTPException(409, "Project changed or missing project binding; reopen project")


def authorize_editor(request: Request) -> None:
    require_project_context(request)
    operation = "readEditor" if request.method == "GET" else "modifyEditor"
    if request.url.path.endswith("/release"):
        operation = "releaseEditor"
    enforce(request, operation)


def authorize_inference(
    request: Request,
    base_url: str,
    profile_id: str = "",
    *,
    channel: str = "metadataChannel",
    classification: str = "internalData",
) -> str:
    parsed = urlsplit(base_url)
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        local = bool(addresses) and all(
            ipaddress.ip_address(a[4][0]).is_loopback for a in addresses
        )
    except OSError as exc:
        raise HTTPException(400, "Inference destination cannot be resolved") from exc
    enforce(
        request,
        "sendEditorInference",
        {
            "destination": "localEndpoint" if local else "remoteEndpoint",
            "classification": classification,
            "channel": channel,
        },
        {"profileId": profile_id},
    )
    return "localEndpoint" if local else "remoteEndpoint"
