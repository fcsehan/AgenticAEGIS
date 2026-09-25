"""Provider profile configuration API. Responses never include credential values."""

from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from aegis.editor.llm_provider import LLMClient, LLMProviderInfo, open_provider_request
from aegis.editor.mediation import authorize_editor, authorize_inference, require_project_context
from aegis.editor.provider_config import InferenceProfile, ProviderSettings, ProviderStore

router = APIRouter(
    prefix="/api/llm", tags=["provider-settings"], dependencies=[Depends(authorize_editor)]
)


def store(request: Request) -> ProviderStore:
    result: ProviderStore | None = getattr(request.app.state, "provider_store", None)
    if result is None:
        raise HTTPException(503, "Provider settings require the editor application")
    return result


def provider_info(profile: InferenceProfile) -> LLMProviderInfo:
    info = LLMProviderInfo(
        id=profile.id,
        name=profile.name,
        type=profile.type,
        base_url=profile.base_url,
        protocol=profile.protocol,
        secret_env=profile.secret_env,
        allow_private=profile.allow_private,
    )

    info.secret_env = profile.secret_env  # Explicit profile settings override legacy CLI defaults.
    return info


def configured_client(request: Request, provider_id: str, model_id: str) -> LLMClient:
    require_project_context(request)
    settings = store(request).load()
    profile = next((p for p in settings.profiles if p.id == provider_id and p.enabled), None)
    if profile is None:
        raise HTTPException(400, "Select an enabled provider")
    model = model_id.strip() or profile.model
    if not model:
        raise HTTPException(400, "Select or enter a model ID")
    if profile.secret_env and not os.getenv(profile.secret_env):
        raise HTTPException(400, "Provider credential environment variable is not set")
    from aegis.editor.api import get_state

    path = request.url.path
    domain = get_state().domains.get(request.path_params.get("domain_id", ""))
    classification = domain.classification if domain else "confidentialData"
    if path.endswith("/capability"):
        channel, classification = "capabilityChannel", "internalData"
    elif path == "/api/dip/jobs":
        channel = "documentChannel"
    elif path.endswith(("/generate", "/refine")):
        channel = "authoringChannel"
    else:
        raise HTTPException(403, "Unmodeled inference channel")
    destination = authorize_inference(
        request, profile.base_url, profile.id, channel=channel, classification=classification
    )
    info = provider_info(profile)
    info.loopback_only = destination == "localEndpoint"
    return LLMClient(
        info,
        model,
        timeout=profile.timeout,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
    )


def probe(profile: InferenceProfile, loopback_only: bool = False) -> dict[str, Any]:
    info = provider_info(profile)
    info.loopback_only = loopback_only
    result = info.to_dict()
    result.update({"testedAt": datetime.now(UTC).isoformat(), "models": [], "available": False})
    if not profile.enabled:
        return {**result, "error": "Provider disabled", "errorType": "disabled"}
    headers = {"Content-Type": "application/json"}
    if profile.secret_env:
        secret = os.getenv(profile.secret_env, "")
        if not secret:
            return {**result, "error": "Credential is not configured", "errorType": "auth"}
        if profile.protocol == "anthropic":
            headers.update({"x-api-key": secret, "anthropic-version": "2023-06-01"})
        else:
            headers["Authorization"] = f"Bearer {secret}"
    try:
        req = urllib.request.Request(f"{profile.base_url}/models", headers=headers)
        with open_provider_request(req, info, min(profile.timeout, 10)) as response:
            data = json.loads(response.read(2_000_000))
        models = [
            {
                "id": item["id"],
                "name": item.get("display_name", item["id"]),
                "contextLength": item.get("context_length"),
            }
            for item in data["data"]
            if isinstance(item.get("id"), str)
        ]
        result.update({"available": True, "models": models, "capabilityStatus": "untested"})
    except urllib.error.HTTPError as exc:
        result.update(
            {
                "error": f"Provider HTTP {exc.code}",
                "errorType": "auth" if exc.code in {401, 403} else "http",
            }
        )
    except socket.gaierror:
        result.update({"error": "DNS resolution failed", "errorType": "dns"})
    except ssl.SSLError:
        result.update({"error": "TLS certificate or handshake failed", "errorType": "tls"})
    except TimeoutError:
        result.update({"error": "Provider timed out", "errorType": "timeout"})
    except (ConnectionError, urllib.error.URLError):
        result.update({"error": "Provider connection failed", "errorType": "connection"})
    except (ValueError, KeyError, TypeError, OSError):
        result.update(
            {"error": "Invalid response or disallowed destination", "errorType": "invalid"}
        )
    return result


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    settings = store(request).load()
    return {
        **settings.model_dump(by_alias=True),
        "credentialStatus": {
            p.id: bool(p.secret_env and os.getenv(p.secret_env)) for p in settings.profiles
        },
    }


@router.put("/settings")
def put_settings(body: ProviderSettings, request: Request) -> dict[str, Any]:
    try:
        store(request).save(body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    request.app.state.capabilities.clear()
    return get_settings(request)


@router.post("/profiles/{profile_id}/probe")
async def probe_profile(profile_id: str, request: Request) -> dict[str, Any]:
    profile = next((p for p in store(request).load().profiles if p.id == profile_id), None)
    if profile is None:
        raise HTTPException(404, "Provider profile not found")
    try:
        destination = authorize_inference(request, profile.base_url, profile.id)
    except HTTPException as exc:
        return {
            **provider_info(profile).to_dict(),
            "available": False,
            "error": str(exc.detail),
            "errorType": "policy",
        }
    result = await run_in_threadpool(probe, profile, destination == "localEndpoint")
    model_ids = {model["id"] for model in result.get("models", [])}
    request.app.state.capabilities = {
        item
        for item in request.app.state.capabilities
        if item[1] != profile_id or result["available"] and item[2] in model_ids
    }
    return result


@router.post("/profiles/{profile_id}/capability")
async def test_capability(
    profile_id: str, body: dict[str, str], request: Request
) -> dict[str, Any]:
    """Explicit, small tool-call test; it does not transmit domain content."""
    revision_before = store(request).load().revision
    client = configured_client(request, profile_id, body.get("model", ""))
    request.app.state.capabilities.discard((revision_before, profile_id, client.model_id))
    tool = {
        "type": "function",
        "function": {
            "name": "report_capability",
            "description": "Report structured tool support",
            "parameters": {
                "type": "object",
                "properties": {"supported": {"type": "boolean"}},
                "required": ["supported"],
                "additionalProperties": False,
            },
        },
    }
    try:
        response = await run_in_threadpool(
            client.chat,
            [
                {
                    "role": "user",
                    "content": (
                        "Call report_capability with supported=true. Do not answer with prose."
                    ),
                }
            ],
            [tool],
        )
        calls = response["choices"][0]["message"].get("tool_calls", [])
        passed = any(
            c["function"]["name"] == "report_capability"
            and json.loads(c["function"]["arguments"]) == {"supported": True}
            for c in calls
        )
    except Exception:
        # No raw provider error bodies: they may contain secrets or prompt contents.
        return {"passed": False, "detail": "Provider request or structured tool response failed"}
    settings = store(request).load()
    if settings.revision != revision_before:
        raise HTTPException(409, "Provider settings changed during capability test; repeat")
    if passed:
        request.app.state.capabilities.add((settings.revision, profile_id, client.model_id))
    return {"passed": passed, "detail": "Tool call verified" if passed else "No valid tool call"}
