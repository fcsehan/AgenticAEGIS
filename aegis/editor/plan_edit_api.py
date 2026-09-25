"""Structured source-preserving editor for the four existing plan predicates."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aegis.editor.api import SourceRequest, get_state, save_sources
from aegis.editor.mediation import authorize_editor
from aegis.editor.source_edit import replace_assertion
from aegis.kb.meld_loader import parse_meld

router = APIRouter(prefix="/api/domains", dependencies=[Depends(authorize_editor)])
KINDS = ("obligateSequence", "forbidAggregate", "obligateWithin", "requirePrecondition")
ALIASES = dict(
    zip(
        ("obligate-sequence", "forbid-aggregate", "obligate-within", "require-precondition"),
        KINDS,
        strict=True,
    )
)


def term(value: Any) -> str:
    if isinstance(value, tuple):
        return "(" + " ".join(term(v) for v in value) + ")"
    if isinstance(value, int) or re.fullmatch(r"[A-Za-z_*?][A-Za-z0-9_*?:-]*", str(value)):
        return str(value)
    return json.dumps(value)


def constraints(sources: dict[str, str]) -> list[dict[str, Any]]:
    result = []
    for filename, text in sources.items():
        for number, assertion in enumerate(parse_meld(text), 1):
            kind = ALIASES.get(str(assertion[0]), assertion[0])
            if kind not in KINDS or len(assertion) != 3:
                continue
            result.append(
                {
                    "id": hashlib.sha256(f"{filename}:{number}".encode()).hexdigest()[:20],
                    "filename": filename,
                    "number": number,
                    "kind": kind,
                    "action": term(assertion[1]),
                    "argument": term(assertion[2]),
                }
            )
    return result


class PlanEdit(BaseModel):
    revision: str
    id: str | None = None
    operation: Literal["save", "delete"] = "save"
    kind: Literal["obligateSequence", "forbidAggregate", "obligateWithin", "requirePrecondition"]
    action: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,99}$")
    argument: str = Field(min_length=1, max_length=2000)


@router.get("/{domain_id}/plan-constraints")
def get_constraints(domain_id: str) -> dict[str, Any]:
    store = get_state().sources.get(domain_id)
    if store is None:
        raise HTTPException(404, "Source domain not found")
    sources, revision = store.load()
    return {"revision": revision, "constraints": constraints(sources)}


@router.post("/{domain_id}/plan-constraints")
def edit_constraint(domain_id: str, body: PlanEdit) -> dict[str, Any]:
    state = get_state()
    store = state.sources.get(domain_id)
    if store is None:
        raise HTTPException(404, "Source domain not found")
    sources, revision = store.load()
    if body.revision != revision:
        raise HTTPException(409, "Domain changed; reload constraints")
    if body.action not in state.domains[domain_id].action_types:
        raise HTTPException(422, "Select an existing action type")
    expression = f"({body.kind} {body.action} {body.argument})"
    try:
        parsed = parse_meld(expression)
        if len(parsed) != 1 or len(parsed[0]) != 3:
            raise ValueError("Expected one plan constraint with two arguments")
        argument = parsed[0][2]
        if (
            body.kind == "obligateSequence"
            and argument not in state.domains[domain_id].action_types
        ):
            raise ValueError("Select an existing successor action")
        if body.kind == "forbidAggregate" and (not isinstance(argument, int) or argument < 0):
            raise ValueError("Maximum count must be a nonnegative integer")
        if body.kind == "obligateWithin" and not (
            isinstance(argument, int)
            and argument >= 0
            or argument in ("immediate", "same-session", "end-of-plan")
        ):
            raise ValueError("Use seconds or immediate/same-session/end-of-plan")
        if body.kind == "requirePrecondition" and not isinstance(argument, tuple):
            raise ValueError("Precondition must be a MELD state term, e.g. (testStatus passed)")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.id:
        previous = next((c for c in constraints(sources) if c["id"] == body.id), None)
        if previous is None:
            raise HTTPException(409, "Constraint changed or disappeared")
        name = previous["filename"]
        sources[name] = replace_assertion(
            sources[name], previous["number"], "" if body.operation == "delete" else expression
        )
    else:
        if body.operation == "delete":
            raise HTTPException(422, "Select a constraint to delete")
        schema = (
            2 if any(("aegis-schema-version", 2) in parse_meld(s) for s in sources.values()) else 1
        )
        filename = "EditorPlanConstraints.meld"
        sources[filename] = (
            sources.get(
                filename, f"(aegis-schema-version {schema})\n(case EditorPlanConstraintsMt)\n"
            )
            + expression
            + "\n"
        )
    return save_sources(domain_id, SourceRequest(revision=revision, sources=sources))
