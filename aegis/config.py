"""AEGIS-1302: Configuration Management.

Environment-based configuration for all AEGIS components.
Precedence: env vars (AEGIS_*) > defaults.

Secret management (AEGIS-1304): API keys via env vars only,
never in config files or logs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GuardConfig:
    """Guard engine configuration."""

    domains_path: Path = field(
        default_factory=lambda: Path(os.getenv("AEGIS_DOMAINS_PATH", "./domains"))
    )
    audit_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("AEGIS_AUDIT_PATH", "./audit/audit.jsonl")
        )
    )
    audit_rotation_mb: int = field(
        default_factory=lambda: int(os.getenv("AEGIS_AUDIT_ROTATION_MB", "100"))
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("AEGIS_LOG_LEVEL", "INFO")
    )
    max_rejection_loop: int = field(
        default_factory=lambda: int(os.getenv("AEGIS_MAX_REJECTION_LOOP", "3"))
    )


@dataclass
class APIConfig:
    """API server configuration."""

    host: str = field(
        default_factory=lambda: os.getenv("AEGIS_API_HOST", "0.0.0.0")
    )
    port: int = field(
        default_factory=lambda: int(os.getenv("AEGIS_API_PORT", "8420"))
    )
    workers: int = field(
        default_factory=lambda: int(os.getenv("AEGIS_API_WORKERS", "1"))
    )
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("AEGIS_API_CORS_ORIGINS", "").split(",")
            if o.strip()
        ]
    )


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: str = field(
        default_factory=lambda: os.getenv("AEGIS_LLM_PROVIDER", "claude")
    )
    model: str = field(
        default_factory=lambda: os.getenv("AEGIS_LLM_MODEL", "claude-sonnet-4-20250514")
    )
    api_key: str = field(
        default_factory=lambda: os.getenv("AEGIS_LLM_API_KEY", "")
    )
    base_url: str = field(
        default_factory=lambda: os.getenv("AEGIS_LLM_BASE_URL", "")
    )


@dataclass
class AegisConfig:
    """Top-level AEGIS configuration."""

    guard: GuardConfig = field(default_factory=GuardConfig)
    api: APIConfig = field(default_factory=APIConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    def show(self) -> str:
        """Display configuration (secrets masked)."""
        lines = [
            "AEGIS Configuration:",
            "  Guard:",
            f"    domains_path: {self.guard.domains_path}",
            f"    audit_path: {self.guard.audit_path}",
            f"    audit_rotation_mb: {self.guard.audit_rotation_mb}",
            f"    log_level: {self.guard.log_level}",
            f"    max_rejection_loop: {self.guard.max_rejection_loop}",
            "  API:",
            f"    host: {self.api.host}",
            f"    port: {self.api.port}",
            f"    workers: {self.api.workers}",
            f"    cors_origins: {self.api.cors_origins}",
            "  LLM:",
            f"    provider: {self.llm.provider}",
            f"    model: {self.llm.model}",
            f"    api_key: {_mask_secret(self.llm.api_key)}",
            f"    base_url: {self.llm.base_url or '(not set)'}",
        ]
        return "\n".join(lines)


def _mask_secret(value: str) -> str:
    """Mask a secret value for display."""
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "****"
    return value[:4] + "..." + "****"
