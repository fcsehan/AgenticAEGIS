"""Content-addressed MELD drafts with atomic publication of a revision pointer.

Original project files are never overwritten by draft editing. A revision consists
of complete MELD sources, not a lossy projection through legacy NormFrames.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

from aegis.guard.guard import Guard


def source_revision(sources: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(sources, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def read_sources(paths: list[Path]) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in paths}


def validate_sources(sources: dict[str, str]) -> None:
    if not sources or len(sources) > 50:
        raise ValueError("Provide 1–50 MELD files")
    for name, content in sources.items():
        if (
            Path(name).name != name
            or not name.endswith(".meld")
            or name.startswith(".")
            or "\\" in name
            or len(content.encode()) > 2_000_000
        ):
            raise ValueError("Invalid MELD filename or file too large")


class SourceStore:
    def __init__(self, project: Path, domain_id: str, originals: list[Path]) -> None:
        key = hashlib.sha256(domain_id.encode()).hexdigest()[:24]
        self.directory = project / ".aegis-editor" / key
        self.project = project.resolve()
        self.originals = originals
        self._lock = threading.RLock()

    def load(self) -> tuple[dict[str, str], str]:
        if not self.directory.resolve().is_relative_to(self.project):
            raise ValueError("Draft storage escapes project")
        if any(not p.resolve().is_relative_to(self.project) for p in self.originals):
            raise ValueError("Source file escapes project")
        pointer = self.directory / "current.json"
        if pointer.is_symlink():
            raise ValueError("Draft pointer symlinks are not supported")
        if not pointer.exists():
            sources = read_sources(self.originals)
            return sources, source_revision(sources)
        data = json.loads(pointer.read_text(encoding="utf-8"))
        revision = data["revision"]
        if (
            not isinstance(revision, str)
            or len(revision) != 64
            or any(c not in "0123456789abcdef" for c in revision)
        ):
            raise ValueError("Invalid draft revision")
        paths = sorted((self.directory / revision).glob("*.meld"))
        if any(not p.resolve().is_relative_to(self.directory.resolve()) for p in paths):
            raise ValueError("Draft source escapes storage")
        sources = read_sources(paths)
        if not sources or source_revision(sources) != revision:
            raise ValueError("Draft integrity check failed")
        return sources, revision

    def save(self, sources: dict[str, str], expected_revision: str) -> tuple[Guard, str]:
        with self._lock:
            _, current = self.load()
            if current != expected_revision:
                raise ValueError("Revision changed; reload before saving")
            validate_sources(sources)
            self.directory.mkdir(parents=True, exist_ok=True)
            revision = source_revision(sources)
            with tempfile.TemporaryDirectory(dir=self.directory, prefix=".draft-") as tmp:
                stage = Path(tmp)
                for name, content in sources.items():
                    (stage / name).write_text(content, encoding="utf-8")
                # Compilation must succeed before a new pointer is visible.
                guard = Guard.from_meld_files(sorted(stage.glob("*.meld")))
                target = self.directory / revision
                if not target.exists():
                    os.rename(stage, target)
            if source_revision(read_sources(sorted(target.glob("*.meld")))) != revision:
                raise ValueError("Existing snapshot integrity check failed")
            # Rebuild from the permanent path so justification sources survive restart.
            guard = Guard.from_meld_files(sorted(target.glob("*.meld")))
            fd, pointer = tempfile.mkstemp(dir=self.directory, prefix=".current-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump({"revision": revision}, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(pointer, self.directory / "current.json")
            finally:
                Path(pointer).unlink(missing_ok=True)
            return guard, revision

    def guard(self) -> Guard:
        sources, revision = self.load()
        snapshot = self.directory / revision
        if snapshot.is_dir():
            return Guard.from_meld_files(sorted(snapshot.glob("*.meld")))
        return Guard.from_meld_files(self.originals)
