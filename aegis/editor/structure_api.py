"""Source-backed ontology and action-vocabulary edits for schema-1 projects."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aegis.editor.api import SourceRequest, get_state, save_sources
from aegis.editor.mediation import authorize_editor
from aegis.editor.source_edit import rename_symbol, replace_assertion
from aegis.kb.meld_loader import parse_meld

router = APIRouter(prefix="/api/domains", dependencies=[Depends(authorize_editor)])
SYMBOL = r"^[A-Za-z][A-Za-z0-9_-]{0,99}$"


class Parameter(BaseModel):
    name: str = Field(pattern=SYMBOL)
    type: str = Field(default="Thing", pattern=SYMBOL)


class StructureRequest(BaseModel):
    revision: str
    kind: Literal["role", "obligation", "code", "action"]
    operation: Literal["create", "update", "delete"] = "create"
    name: str = Field(pattern=SYMBOL)
    previous: str | None = Field(default=None, pattern=SYMBOL)
    description: str = Field(default="", max_length=4000)
    parent: str | None = Field(default=None, pattern=SYMBOL)
    parameters: list[Parameter] = Field(default_factory=list, max_length=30)


def mentions(value: Any, name: str) -> bool:
    return value == name or isinstance(value, tuple) and any(mentions(v, name) for v in value)


@router.post("/{domain_id}/structure")
def edit_structure(domain_id: str, body: StructureRequest) -> dict[str, Any]:
    state = get_state()
    source = state.sources.get(domain_id)
    if source is None:
        raise HTTPException(404, "Source domain not found")
    sources, revision = source.load()
    if revision != body.revision:
        raise HTTPException(409, "Domain changed; reopen the editor")
    assertions = {name: parse_meld(text) for name, text in sources.items()}
    if any(a == ("aegis-schema-version", 2) for values in assertions.values() for a in values):
        raise HTTPException(409, "Use the MELD source editor for schema-2 structure")
    previous = body.previous or body.name
    if body.parent:
        if body.parent not in {o.name for o in state.domains[domain_id].obligation_types}:
            raise HTTPException(422, "Select a declared obligation type as parent")
        inheritance = state.guards[domain_id]._inheritance
        if body.parent == previous or (
            inheritance is not None and inheritance.is_subtype(body.parent, previous)
        ):
            raise HTTPException(422, "Parent assignment would create a cycle")
    existing = any(mentions(a, body.name) for values in assertions.values() for a in values)
    if existing and (body.operation == "create" or previous != body.name):
        raise HTTPException(409, "Symbol already exists")
    if body.operation in {"update", "delete"} and not any(
        mentions(a, previous) for values in assertions.values() for a in values
    ):
        raise HTTPException(404, "Symbol does not exist")
    for filename, values in assertions.items():
        remove = []
        for number, assertion in enumerate(values, 1):
            own = len(assertion) >= 3 and assertion[1] == previous
            declaration = own and assertion[0] in {"isa", "genls", "comment", "actionParameter"}
            if body.operation == "delete":
                if mentions(assertion, previous) and not declaration:
                    raise HTTPException(
                        409, "Symbol is still referenced by rules or other declarations"
                    )
                if declaration:
                    remove.append(number)
            elif body.operation == "update":
                if own and assertion[0] == "comment":
                    remove.append(number)
                if body.kind == "obligation" and own and assertion[0] == "genls":
                    remove.append(number)
                if (
                    body.kind == "role"
                    and own
                    and assertion[0] == "isa"
                    and assertion[2] in {o.name for o in state.domains[domain_id].obligation_types}
                ):
                    remove.append(number)
                if body.kind == "action" and own and assertion[0] == "actionParameter":
                    remove.append(number)
        text = sources[filename]
        for number in reversed(remove):
            text = replace_assertion(text, number, "")
        if body.operation == "update" and previous != body.name:
            text = rename_symbol(text, previous, body.name)
        sources[filename] = text
    if body.operation != "delete":
        lines = []
        if body.operation == "create":
            collection = {
                "role": "EditorRole",
                "obligation": "ObligationType",
                "code": "CodeOfConduct",
                "action": "ActionType",
            }[body.kind]
            lines.append(f"(isa {body.name} {collection})")
            if body.kind == "role":
                lines.append("(genls EditorRole IntelligentAgent)")
        if body.kind == "obligation" and body.parent:
            lines.append(f"(genls {body.name} {body.parent})")
        if body.kind == "role" and body.parent:
            lines.append(f"(isa {body.name} {body.parent})")
        if body.kind == "action":
            if len({p.name for p in body.parameters}) != len(body.parameters):
                raise HTTPException(422, "Parameter names must be unique")
            lines.extend(
                f"(actionParameter {body.name} {p.name} {p.type})" for p in body.parameters
            )
        lines.append(f"(comment {body.name} {json.dumps(body.description, ensure_ascii=False)})")
        filename = "EditorStructure.meld"
        sources[filename] = (
            sources.get(filename, "(aegis-schema-version 1)\n(case EditorStructureMt)\n")
            + "\n".join(lines)
            + "\n"
        )
    return save_sources(domain_id, SourceRequest(revision=revision, sources=sources))


class CodePrevalenceRequest(BaseModel):
    revision: str
    codes: list[str] = Field(max_length=100)


@router.post("/{domain_id}/code-prevalence")
def save_code_prevalence(domain_id: str, body: CodePrevalenceRequest) -> dict[str, Any]:
    state = get_state()
    source = state.sources.get(domain_id)
    if source is None:
        raise HTTPException(404, "Source domain not found")
    sources, revision = source.load()
    if body.revision != revision:
        raise HTTPException(409, "Domain changed; reload before editing precedence")
    if any(("aegis-schema-version", 2) in parse_meld(text) for text in sources.values()):
        raise HTTPException(
            409, "Schema 2 uses formula priorities; edit its priority declarations in MELD"
        )
    known = {code.name for code in state.domains[domain_id].codes}
    if len(set(body.codes)) != len(body.codes) or any(code not in known for code in body.codes):
        raise HTTPException(422, "Provide unique, declared codes in highest-to-lowest order")
    for name, text in sources.items():
        indices = [i for i, a in enumerate(parse_meld(text), 1) if a[0] == "codePrevalence"]
        for index in reversed(indices):
            text = replace_assertion(text, index, "")
        sources[name] = text
    if body.codes:
        filename = "EditorCodePrevalence.meld"
        sources[filename] = (
            sources.get(filename, "(aegis-schema-version 1)\n(case EditorCodePrevalenceMt)\n")
            + "(codePrevalence "
            + " ".join(body.codes)
            + ")\n"
        )
    return save_sources(domain_id, SourceRequest(revision=revision, sources=sources))
