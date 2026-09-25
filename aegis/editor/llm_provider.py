"""AEGIS-1401: LLM Provider Detection & Configuration.

Detects local inference servers (LM Studio, Ollama, vLLM) via HTTP probe,
lists available models, and exposes configured remote providers (Anthropic, OpenAI).
Uses urllib.request (no new dependencies) consistent with orchestrator.py.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import logging
import os
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT = 2  # seconds


@dataclass
class ModelInfo:
    """A model available from a provider."""

    id: str
    name: str
    context_length: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "contextLength": self.context_length,
        }


@dataclass
class LLMProviderInfo:
    """A detected or configured LLM provider."""

    id: str
    name: str
    type: str  # "local" | "remote"
    base_url: str
    available: bool = False
    models: list[ModelInfo] = field(default_factory=list)
    error: str | None = None
    protocol: str = "openai"
    secret_env: str = ""
    allow_private: bool = True
    loopback_only: bool = False

    def __post_init__(self) -> None:
        # Preserve CLI callers for canonical vendors only. An arbitrary compatible
        # endpoint never inherits a vendor credential merely from its protocol.
        canonical = {
            ("openai", "https://api.openai.com/v1"): "OPENAI_API_KEY",
            ("anthropic", "https://api.anthropic.com"): "ANTHROPIC_API_KEY",
            ("anthropic", "https://api.anthropic.com/v1"): "ANTHROPIC_API_KEY",
        }
        if not self.secret_env and self.type == "remote":
            self.secret_env = canonical.get((self.id, self.base_url.rstrip("/")), "")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "baseUrl": self.base_url,
            "available": self.available,
            "models": [m.to_dict() for m in self.models],
        }
        if self.error:
            result["error"] = self.error
        return result


# ── Local Provider Definitions ────────────────────────────────────

_LOCAL_PROVIDERS = [
    {
        "id": "lm-studio",
        "name": "LM Studio",
        "base_url": "http://localhost:1234/v1",
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "base_url": "http://localhost:11434/v1",
    },
    {
        "id": "vllm",
        "name": "vLLM",
        "base_url": "http://localhost:8000/v1",
    },
]


# ── Detection ─────────────────────────────────────────────────────


def _probe_models(base_url: str) -> list[ModelInfo]:
    """Probe a provider's /models endpoint. Returns model list or empty."""
    url = f"{base_url}/models"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT) as resp:
            data: dict[str, Any] = json.loads(resp.read())
            models: list[ModelInfo] = []
            for m in data.get("data", []):
                models.append(
                    ModelInfo(
                        id=m.get("id", ""),
                        name=m.get("id", ""),
                        context_length=m.get("context_length"),
                    )
                )
            return models
    except Exception:
        return []


def detect_local_providers() -> list[LLMProviderInfo]:
    """Probe local inference servers and return their status.

    Probes are non-fatal: unavailable providers are returned with
    ``available=False`` and an error message.
    """
    results: list[LLMProviderInfo] = []
    for spec in _LOCAL_PROVIDERS:
        provider = LLMProviderInfo(
            id=spec["id"],
            name=spec["name"],
            type="local",
            base_url=spec["base_url"],
        )
        try:
            models = _probe_models(spec["base_url"])
            if models:
                provider.available = True
                provider.models = models
            else:
                provider.error = "No models available or server not responding"
        except Exception as e:
            provider.error = str(e)

        results.append(provider)
    return results


def get_remote_providers() -> list[LLMProviderInfo]:
    """Return configured remote providers based on environment variables."""
    providers: list[LLMProviderInfo] = []

    if os.environ.get("ANTHROPIC_API_KEY"):
        providers.append(
            LLMProviderInfo(
                id="anthropic",
                protocol="anthropic",
                secret_env="ANTHROPIC_API_KEY",
                name="Anthropic",
                type="remote",
                base_url="https://api.anthropic.com",
                available=True,
                models=[
                    ModelInfo(id="claude-sonnet-4-6", name="Claude Sonnet 4.6"),
                    ModelInfo(id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5"),
                ],
            )
        )

    if os.environ.get("OPENAI_API_KEY"):
        providers.append(
            LLMProviderInfo(
                id="openai",
                secret_env="OPENAI_API_KEY",
                name="OpenAI",
                type="remote",
                base_url="https://api.openai.com/v1",
                available=True,
                models=[
                    ModelInfo(id="gpt-4o", name="GPT-4o"),
                    ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini"),
                ],
            )
        )

    return providers


def get_all_providers() -> list[LLMProviderInfo]:
    """Detect all local + remote providers."""
    return detect_local_providers() + get_remote_providers()


# ── LLM Client ────────────────────────────────────────────────────


class LLMClient:
    """Minimal LLM client for MELD authoring.

    Sends chat completion requests with tool definitions.
    Compatible with OpenAI-format APIs (LM Studio, Ollama, vLLM, OpenAI).

    For Anthropic, uses the Messages API format.
    """

    def __init__(
        self,
        provider: LLMProviderInfo,
        model: str,
        *,
        timeout: int = 120,
        max_tokens: int = 4000,
        temperature: float = 0,
    ) -> None:
        self._provider = provider
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature

    @property
    def provider_id(self) -> str:
        return self._provider.id

    @property
    def model_id(self) -> str:
        return self._model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request.

        Returns the raw response dict from the API.
        """
        if self._provider.protocol == "anthropic" or self._provider.id == "anthropic":
            return self._chat_anthropic(messages, tools)
        return self._chat_openai(messages, tools)

    def _chat_openai(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """OpenAI-compatible chat completion."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        data = json.dumps(payload).encode()
        headers: dict[str, str] = {"Content-Type": "application/json"}

        api_key = os.environ.get(self._provider.secret_env, "") if self._provider.secret_env else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(
            f"{self._provider.base_url}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        with open_provider_request(req, self._provider, self._timeout) as resp:
            result: dict[str, Any] = json.loads(resp.read())
            return result

    def _chat_anthropic(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Anthropic Messages API, adapted to return OpenAI-compatible structure."""
        api_key = os.environ.get(self._provider.secret_env, "") if self._provider.secret_env else ""
        if not api_key:
            raise ValueError("Provider credential is not configured")

        # Separate system message
        system_msg = ""
        chat_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append(msg)

        # Convert tools from OpenAI format to Anthropic format
        anthropic_tools: list[dict[str, Any]] = []
        if tools:
            for tool in tools:
                fn = tool.get("function", tool)
                anthropic_tools.append(
                    {
                        "name": fn["name"],
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    }
                )

        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": chat_messages,
        }
        if system_msg:
            payload["system"] = system_msg
        if anthropic_tools:
            payload["tools"] = anthropic_tools

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._provider.base_url.rstrip('/')}/messages"
            if self._provider.base_url.rstrip("/").endswith("/v1")
            else f"{self._provider.base_url.rstrip('/')}/v1/messages",
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with open_provider_request(req, self._provider, self._timeout) as resp:
            raw: dict[str, Any] = json.loads(resp.read())

        return _anthropic_to_openai_format(raw)


def _anthropic_to_openai_format(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert Anthropic Messages API response to OpenAI-compatible format."""
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for block in raw.get("content", []):
        if block["type"] == "text":
            text_parts.append(block["text"])
        elif block["type"] == "tool_use":
            tool_calls.append(
                {
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block["input"]),
                    },
                }
            )

    message: dict[str, Any] = {"role": "assistant", "content": "\n".join(text_parts)}
    if tool_calls:
        message["tool_calls"] = tool_calls

    return {"choices": [{"message": message}]}


class ProviderResponse:
    """Bounded HTTP response that closes both response and pinned connection."""

    def __init__(
        self, connection: http.client.HTTPConnection, response: http.client.HTTPResponse
    ) -> None:
        self.connection = connection
        self.response = response

    def __enter__(self) -> ProviderResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        self.response.close()
        self.connection.close()

    def read(self, size: int = -1) -> bytes:
        limit = min(size, 10_000_000) if size >= 0 else 10_000_000
        data = self.response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Provider response exceeds the response limit")
        return data


def open_provider_request(
    request: urllib.request.Request, provider: LLMProviderInfo, timeout: int
) -> ProviderResponse:
    """Pin the connection to validated IPs; preserve Host/SNI and verify TLS.

    No proxies or redirects. Destination checks and connection use the same DNS
    answer, and local mediation cannot become a non-loopback transmission.
    """
    parsed = urlsplit(request.full_url)
    origin = urlsplit(provider.base_url)
    if (parsed.scheme, parsed.hostname, parsed.port) != (
        origin.scheme,
        origin.hostname,
        origin.port,
    ):
        raise ValueError("Request target does not match provider")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ValueError("Invalid provider URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    for _, _, _, _, address_info in addresses:
        address = ipaddress.ip_address(address_info[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if address.is_link_local or address.is_multicast or address.is_unspecified:
            raise ValueError("Provider destination is not allowed")
        if provider.loopback_only and not address.is_loopback:
            raise ValueError("Provider no longer matches its local mediation decision")
        if parsed.scheme == "http" and address.is_global:
            raise ValueError("Public provider destinations require HTTPS")
        if not address.is_global and not address.is_private and not address.is_loopback:
            raise ValueError("Special-use provider destination is not allowed")
        if not provider.allow_private and not address.is_global:
            raise ValueError("Private provider destination requires explicit opt-in")
    connection = http.client.HTTPConnection(parsed.hostname, port, timeout=timeout)
    connected: socket.socket | None = None
    last_error: OSError | None = None
    for family, socktype, proto, _, address_info in addresses:
        candidate = socket.socket(family, socktype, proto)
        candidate.settimeout(timeout)
        try:
            candidate.connect(address_info)
            connected = candidate
            break
        except OSError as exc:
            candidate.close()
            last_error = exc
    if connected is None:
        raise last_error or OSError("No provider addresses")
    try:
        if parsed.scheme == "https":
            connected = ssl.create_default_context().wrap_socket(
                connected, server_hostname=parsed.hostname
            )
        connection.sock = connected
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        connection.request(
            request.get_method(), path, body=request.data, headers=dict(request.header_items())
        )
        response = connection.getresponse()
        if response.status >= 300:
            error = urllib.error.HTTPError(
                request.full_url, response.status, "Provider request failed", response.headers, None
            )
            response.close()
            raise error
        return ProviderResponse(connection, response)
    except BaseException:
        connected.close()
        connection.close()
        raise
