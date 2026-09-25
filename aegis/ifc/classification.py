"""AEGIS-1804: Workspace Classification Manifest.

Provides a file-level classification map for workspaces, enabling
preToolUse hooks (Copilot CLI, OpenCode) to block reads on classified
files before execution — the only viable enforcement point since
postToolUse hooks are observational-only.

Manifest format (.aegis-classification.json)::

    {
        "version": 1,
        "default_classification": "public",
        "files": {
            "intel/secret_briefing.txt": "secret",
            "logs/audit.log": "internal"
        },
        "patterns": {
            "*.secret": "secret",
            "*.classified": "confidential"
        }
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = ".aegis-classification.json"


@dataclass(frozen=True, slots=True)
class ClassificationManifest:
    """Parsed workspace classification manifest.

    File entries take precedence over pattern matches.
    Patterns use ``fnmatch`` semantics.
    """

    version: int
    default_classification: str
    files: dict[str, str]
    patterns: dict[str, str]

    def classify(self, file_path: str) -> str:
        """Return the classification for *file_path*.

        Resolution order:
        1. Exact match in ``files`` dict
        2. First matching pattern in ``patterns`` dict
        3. ``default_classification``
        """
        # Normalize path separators
        normalized = file_path.replace("\\", "/").strip("/")

        # 1. Exact file entry (try both normalized and original)
        if normalized in self.files:
            return self.files[normalized]
        if file_path in self.files:
            return self.files[file_path]

        # 2. Pattern matching (fnmatch against the basename and full path)
        for pattern, classification in self.patterns.items():
            if fnmatch(normalized, pattern) or fnmatch(
                Path(normalized).name, pattern
            ):
                return classification

        # 3. Default
        return self.default_classification

    @classmethod
    def load(cls, path: Path) -> ClassificationManifest:
        """Load a manifest from a JSON file.

        Raises:
            FileNotFoundError: If *path* does not exist.
            ValueError: If the manifest is malformed.
        """
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls._parse(raw)

    @classmethod
    def load_or_default(cls, workspace_root: Path) -> ClassificationManifest:
        """Load from workspace root or return a permissive default."""
        manifest_path = workspace_root / MANIFEST_FILENAME
        if manifest_path.exists():
            return cls.load(manifest_path)
        return cls(
            version=1,
            default_classification="public",
            files={},
            patterns={},
        )

    @classmethod
    def _parse(cls, raw: dict[str, Any]) -> ClassificationManifest:
        """Parse and validate a raw manifest dict."""
        version = raw.get("version", 1)
        if not isinstance(version, int) or version < 1:
            raise ValueError(f"Invalid manifest version: {version!r}")

        default = raw.get("default_classification", "public")
        if not isinstance(default, str):
            raise ValueError(
                f"default_classification must be a string, got {type(default).__name__}"
            )

        files_raw = raw.get("files", {})
        if not isinstance(files_raw, dict):
            raise ValueError("files must be a dict")
        files = {str(k): str(v) for k, v in files_raw.items()}

        patterns_raw = raw.get("patterns", {})
        if not isinstance(patterns_raw, dict):
            raise ValueError("patterns must be a dict")
        patterns = {str(k): str(v) for k, v in patterns_raw.items()}

        return cls(
            version=version,
            default_classification=default,
            files=files,
            patterns=patterns,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "version": self.version,
            "default_classification": self.default_classification,
            "files": dict(self.files),
            "patterns": dict(self.patterns),
        }

    @classmethod
    def from_workspace_files(
        cls,
        files: dict[str, str],
        *,
        default_classification: str = "public",
    ) -> ClassificationManifest:
        """Build a manifest from a {path: classification} mapping.

        Used by the red-team pipeline to auto-generate manifests from
        scenario workspace files.
        """
        return cls(
            version=1,
            default_classification=default_classification,
            files=dict(files),
            patterns={},
        )
