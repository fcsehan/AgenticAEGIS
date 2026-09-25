"""Edits supported legacy rules by changing MELD, not detached Python norms."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aegis.editor.api import SourceRequest, get_state, save_sources
from aegis.editor.mediation import authorize_editor
from aegis.editor.meld_writer import _MODALITY_TO_PREDICATE
from aegis.editor.source_edit import replace_assertion
from aegis.guard.guard import _detect_schema_version
from aegis.kb.meld_loader import extract_norm, parse_meld

router = APIRouter(prefix="/api/domains", dependencies=[Depends(authorize_editor)])


class RuleEditRequest(BaseModel):
    revision: str
    code: str = ""
    agent_role: str = Field(alias="agentRole")
    modality: Literal["OBLIGATORY", "FORBIDDEN", "PERMITTED"]
    proposition: str = Field(min_length=1, max_length=2000)


class DeleteRuleRequest(BaseModel):
    revision: str


def rule_edit(
    domain_id: str,
    body: RuleEditRequest | DeleteRuleRequest,
    rule_id: str | None,
    delete: bool = False,
) -> dict[str, Any]:
    state = get_state()
    source = state.sources.get(domain_id)
    domain = state.domains.get(domain_id)
    if source is None or domain is None:
        raise HTTPException(404, "Source domain not found")
    sources, revision = source.load()
    if body.revision != revision:
        raise HTTPException(409, "Domain changed; reopen the rule")
    # Never serialize a schema-2 formula through the legacy form.
    guard = state.guards[domain_id]
    if not guard._norms and any(_detect_schema_version(p) == 2 for p in source.originals):
        raise HTTPException(409, "Use the MELD editor for schema-2 formulas")
    expression = ""
    try:
        if isinstance(body, RuleEditRequest):
            for symbol in (body.agent_role, body.code):
                if symbol and not re.fullmatch(r"[A-Za-z_*?][A-Za-z0-9_*?:-]*", symbol):
                    raise ValueError("Invalid MELD identifier")
            predicate = _MODALITY_TO_PREDICATE[body.modality]
            if body.code:
                expression = f"({predicate} {body.code} {body.agent_role} ({body.proposition}))"
            else:
                expression = (
                    f"({predicate.removesuffix('-WRT')} {body.agent_role} ({body.proposition}))"
                )
            assertions = parse_meld(expression)
            if (
                len(assertions) != 1
                or extract_norm(assertions[0], "EditorRulesMt", "<editor>") is None
            ):
                raise ValueError("Expected exactly one normative assertion")
            norm = extract_norm(assertions[0], "EditorRulesMt", "<editor>")
            assert norm is not None
            schema = guard._registry.get_schema(str(norm.proposition[0]))
            if schema is None or len(norm.proposition) - 1 != len(schema.parameters):
                raise ValueError("Action and parameter count must match domain vocabulary")
            if body.agent_role not in {r.name for r in domain.roles} and body.agent_role != "*":
                raise ValueError("Select a declared role")
            if body.code and body.code not in {c.name for c in domain.codes}:
                raise ValueError("Select a declared code of conduct")
            for parameter, value in zip(schema.parameters, norm.proposition[1:], strict=True):
                if (
                    isinstance(value, str)
                    and not value.startswith("?")
                    and parameter.type_name != "Thing"
                    and guard._inheritance is not None
                    and not guard._inheritance.is_instance(value, parameter.type_name)
                ):
                    raise ValueError(f"Unknown or incorrectly typed parameter: {parameter.name}")
        if rule_id:
            previous = next((r for r in domain.rules if r.id == rule_id), None)
            if previous is None:
                raise ValueError("Rule no longer exists")
            file_path, number = previous.source.rsplit(":", 1)
            filename = Path(file_path).name
            sources[filename] = replace_assertion(
                sources[filename], int(number), "" if delete else expression
            )
        else:
            filename = "EditorRules.meld"
            sources[filename] = (
                sources.get(filename, "(aegis-schema-version 1)\n(case EditorRulesMt)\n")
                + expression
                + "\n"
            )
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return save_sources(domain_id, SourceRequest(revision=revision, sources=sources))


@router.post("/{domain_id}/source-rules")
def add_rule(domain_id: str, body: RuleEditRequest) -> dict[str, Any]:
    return rule_edit(domain_id, body, None)


@router.put("/{domain_id}/source-rules/{rule_id}")
def update_rule(domain_id: str, rule_id: str, body: RuleEditRequest) -> dict[str, Any]:
    return rule_edit(domain_id, body, rule_id)


@router.post("/{domain_id}/source-rules/{rule_id}/delete")
def delete_rule(domain_id: str, rule_id: str, body: DeleteRuleRequest) -> dict[str, Any]:
    return rule_edit(domain_id, body, rule_id, True)
