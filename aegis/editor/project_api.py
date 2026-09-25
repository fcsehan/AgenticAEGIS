"""Metadata and reviewed MELD package import without overwriting existing domains."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aegis.editor.api import get_state
from aegis.editor.mediation import authorize_editor
from aegis.editor.scenario_api import atomic_json
from aegis.editor.source_store import source_revision, validate_sources
from aegis.guard.guard import Guard

router = APIRouter(prefix="/api", dependencies=[Depends(authorize_editor)])


class Metadata(BaseModel):
    metadata_revision: int = Field(default=0, alias="metadataRevision", ge=0)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=4000)
    archived: bool = False
    classification: Literal["publicData", "internalData", "confidentialData"] = "confidentialData"


def read_domain_metadata(directory: Path, default_name: str) -> dict[str, Any]:
    path = directory / "domain.json"
    if path.is_symlink():
        raise ValueError("Domain metadata symlinks are not supported")
    if path.exists():
        return Metadata.model_validate_json(path.read_text()).model_dump(by_alias=True)
    return Metadata(name=default_name).model_dump(by_alias=True)


@router.get("/domains/{domain_id}/metadata")
def metadata(domain_id: str) -> dict[str, Any]:
    source = get_state().sources.get(domain_id)
    if source is None:
        raise HTTPException(404, "Source domain not found")
    source.load()
    return read_domain_metadata(source.directory, get_state().domains[domain_id].name)


@router.put("/domains/{domain_id}/metadata")
def save_metadata(domain_id: str, body: Metadata) -> dict[str, Any]:
    current = metadata(domain_id)
    if current["metadataRevision"] != body.metadata_revision:
        raise HTTPException(409, "Metadata changed; reload before saving")
    value = body.model_dump(by_alias=True)
    value["metadataRevision"] += 1
    state = get_state()
    atomic_json(state.sources[domain_id].directory / "domain.json", value)
    domain = state.domains[domain_id]
    domain.name = body.name
    domain.description = body.description
    domain.classification = body.classification
    domain.status = "Archived" if body.archived else "Draft"
    return domain.to_dict()


class ImportPackage(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    files: dict[str, str]
    preview_revision: str | None = Field(default=None, alias="previewRevision")


def inspect_package(body: ImportPackage) -> dict[str, Any]:
    project = get_state().project_path
    if project is None:
        raise HTTPException(409, "Open a project first")
    try:
        validate_sources(body.files)
        with tempfile.TemporaryDirectory(prefix="aegis-import-") as temporary:
            root = Path(temporary)
            for name, text in body.files.items():
                (root / name).write_text(text, encoding="utf-8")
            Guard.from_meld_files(sorted(root.glob("*.meld")))
    except Exception as exc:
        raise HTTPException(422, f"MELD package validation failed: {type(exc).__name__}") from exc
    return {
        "revision": source_revision(body.files),
        "files": sorted(body.files),
        "collision": (project / body.name).exists(),
        "status": "Draft",
    }


@router.post("/project/import/preview")
def preview_package(body: ImportPackage) -> dict[str, Any]:
    return inspect_package(body)


@router.post("/project/import")
def import_package(body: ImportPackage) -> dict[str, Any]:
    preview = inspect_package(body)
    if preview["collision"] or body.preview_revision != preview["revision"]:
        raise HTTPException(409, "Review the current preview and choose an unused domain name")
    project = get_state().project_path
    assert project is not None
    stage_root = project / ".aegis-editor"
    if not stage_root.resolve().is_relative_to(project):
        raise HTTPException(409, "Import staging escapes project")
    stage_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=stage_root) as temporary:
        stage = Path(temporary)
        for name, text in body.files.items():
            (stage / name).write_text(text, encoding="utf-8")
        os.rename(stage, project / body.name)
    return get_state().load_project(project)
