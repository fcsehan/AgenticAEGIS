"""Versioned, server-owned inference profiles. Secrets are environment references."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InferenceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=100)
    protocol: Literal["openai", "anthropic"] = "openai"
    type: Literal["local", "remote"] = "local"
    base_url: str = Field(alias="baseUrl")
    secret_env: str = Field(default="", alias="secretEnv", pattern=r"^$|^[A-Z_][A-Z0-9_]*$")
    enabled: bool = True
    allow_private: bool = Field(default=False, alias="allowPrivate")
    model: str = Field(default="", max_length=200)
    temperature: float = Field(default=0, ge=0, le=2)
    max_tokens: int = Field(default=4000, ge=1, le=131072, alias="maxTokens")
    timeout: int = Field(default=120, ge=1, le=300)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use an http(s) base URL without credentials, query or fragment")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("Invalid port") from exc
        return value.rstrip("/")

    @model_validator(mode="after")
    def secure_remote(self) -> InferenceProfile:
        if self.protocol == "anthropic" and self.temperature > 1:
            raise ValueError("Anthropic temperature must be between 0 and 1")
        if self.type == "remote" and not self.base_url.startswith("https://"):
            raise ValueError("Remote providers require HTTPS")
        return self


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    revision: int = Field(default=0, ge=0)
    default_profile: str = Field(default="", alias="defaultProfile")
    profiles: list[InferenceProfile] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_ids(self) -> ProviderSettings:
        ids = [p.id for p in self.profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("Profile IDs must be unique")
        if self.default_profile and not any(
            p.id == self.default_profile and p.enabled for p in self.profiles
        ):
            raise ValueError("Default profile must exist and be enabled")
        return self


def initial_settings() -> ProviderSettings:
    profiles = [
        InferenceProfile(id=key, name=name, baseUrl=url, allowPrivate=True)
        for key, name, url in [
            ("lm-studio", "LM Studio", "http://localhost:1234/v1"),
            ("ollama", "Ollama", "http://localhost:11434/v1"),
            ("vllm", "vLLM", "http://localhost:8000/v1"),
        ]
    ]
    for key, name, url, env in [
        ("openai", "OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY"),
        ("anthropic", "Anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    ]:
        profiles.append(
            InferenceProfile(
                id=key,
                name=name,
                type="remote",
                protocol="anthropic" if key == "anthropic" else "openai",
                baseUrl=url,
                secretEnv=env,
                enabled=bool(os.getenv(env)),
            )
        )
    return ProviderSettings(profiles=profiles)


class ProviderStore:
    """One store per editor process; atomic replacement and optimistic revisions."""

    def __init__(self, directory: Path) -> None:
        self.path = directory / "providers.json"
        self._lock = threading.RLock()

    def load(self) -> ProviderSettings:
        with self._lock:
            if not self.path.exists():
                return initial_settings()
            return ProviderSettings.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, value: ProviderSettings) -> ProviderSettings:
        with self._lock:
            if value.revision != self.load().revision:
                raise ValueError("Settings changed; reload before saving")
            saved = value.model_copy(update={"revision": value.revision + 1})
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".providers-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(saved.model_dump(by_alias=True), stream, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.path)
            finally:
                Path(name).unlink(missing_ok=True)
            return saved
