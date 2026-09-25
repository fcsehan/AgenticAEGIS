"""Portable editor backup with checksums and safe restoration into empty directories."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

_CONFIG_FILES = {"providers.json", "session.json", "editor-audit.jsonl"}
_MAX_ARCHIVE_BYTES = 100_000_000


def backup_project(project: Path, config: Path, destination: Path) -> None:
    project = project.resolve(strict=True)
    if destination.exists():
        raise ValueError("Backup destination already exists")
    entries: dict[str, bytes] = {}
    for path in project.rglob("*"):
        if path.is_symlink():
            raise ValueError("Backup refuses symlinks")
        relative = path.relative_to(project)
        if ".git" in relative.parts or "node_modules" in relative.parts:
            continue
        if path.is_file() and (path.suffix == ".meld" or ".aegis-editor" in relative.parts):
            if any(part.startswith((".draft-", ".current-")) for part in relative.parts):
                continue
            entries[f"project/{relative.as_posix()}"] = path.read_bytes()
    names = _CONFIG_FILES | {
        p.name
        for p in config.glob("editor-audit.jsonl.*")
        if re.fullmatch(r"editor-audit\.jsonl\.\d+", p.name)
    }
    for name in names:
        path = config / name
        if path.is_symlink():
            raise ValueError("Backup refuses config symlinks")
        if path.is_file():
            entries[f"config/{name}"] = path.read_bytes()
    if sum(len(value) for value in entries.values()) > _MAX_ARCHIVE_BYTES:
        raise ValueError("Backup exceeds 100 MB limit")
    manifest = {
        "schemaVersion": 1,
        "projectRoot": str(project),
        "files": {name: hashlib.sha256(value).hexdigest() for name, value in entries.items()},
    }
    with (
        destination.open("xb") as stream,
        ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive,
    ):
        destination.chmod(0o600)
        for name, value in entries.items():
            archive.writestr(name, value)
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))


def restore_project(archive_path: Path, project: Path, config: Path) -> None:
    project = project.absolute()
    config = config.absolute()
    if project.resolve().is_relative_to(config.resolve()) or config.resolve().is_relative_to(
        project.resolve()
    ):
        raise ValueError("Project and config restore roots must not overlap")
    for root in (project, config):
        if root.is_symlink() or root.exists() and any(root.iterdir()):
            raise ValueError("Restore requires empty project and config directories")
    with ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if sum(info.file_size for info in infos) > _MAX_ARCHIVE_BYTES:
            raise ValueError("Expanded backup exceeds 100 MB limit")
        if len({info.filename for info in infos}) != len(infos):
            raise ValueError("Duplicate archive entries")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("schemaVersion") != 1:
            raise ValueError("Unsupported backup schema")
        files = manifest["files"]
        if set(archive.namelist()) != {*files, "manifest.json"}:
            raise ValueError("Unexpected archive members")
        verified: list[tuple[Path, bytes]] = []
        for name, expected in files.items():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or len(path.parts) < 2:
                raise ValueError("Unsafe backup path")
            if path.parts[0] not in {"project", "config"}:
                raise ValueError("Unknown backup namespace")
            if path.parts[0] == "config" and (
                len(path.parts) != 2
                or (
                    path.name not in _CONFIG_FILES
                    and not re.fullmatch(r"editor-audit\.jsonl\.\d+", path.name)
                )
            ):
                raise ValueError("Unknown configuration file")
            content = archive.read(name)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("Backup checksum mismatch")
            root = project if path.parts[0] == "project" else config
            destination = root.joinpath(*path.parts[1:])
            verified.append((destination, content))
        # Validate every entry before writing the first file. Never use extractall.
        for destination, content in verified:
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination.write_bytes(content)
            destination.chmod(0o600)
    session = config / "session.json"
    if session.exists():
        previous = Path(json.loads(session.read_text())["project"])
        old_root = Path(manifest["projectRoot"])
        if previous.is_relative_to(old_root):
            session.write_text(
                json.dumps({"project": str(project.resolve() / previous.relative_to(old_root))})
            )
        else:
            session.unlink()
