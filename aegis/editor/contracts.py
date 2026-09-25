"""Typed response projections; MELD remains the normative source of truth."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ResponseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class RoleResponse(ResponseModel):
    id: str
    name: str
    description: str
    rule_count: int
    obligation_type: str | None


class ObligationResponse(ResponseModel):
    id: str
    name: str
    description: str
    parent_id: str | None
    children: list[ObligationResponse]


class CodeResponse(ResponseModel):
    id: str
    name: str
    description: str
    prevalence: int


class RuleResponse(ResponseModel):
    id: str
    code: str
    agent_role: str
    modality: Literal["PERMITTED", "FORBIDDEN", "OBLIGATORY"]
    proposition: str
    specificity: int
    defeasible: bool
    source: str


class ParameterResponse(ResponseModel):
    name: str
    type: str


class DomainResponse(ResponseModel):
    id: str
    name: str
    description: str
    status: Literal["Draft", "Review", "Published", "Archived"]
    classification: Literal["publicData", "internalData", "confidentialData"]
    roles: list[RoleResponse]
    obligation_types: list[ObligationResponse]
    codes: list[CodeResponse]
    rules: list[RuleResponse]
    meld_files: list[str]
    revision: str
    code_prevalence: list[str]
    action_types: list[str]
    action_schemas: dict[str, list[ParameterResponse]]
    compile_status: Literal["ready", "failed", "uncompiled"]
    load_error: str
    last_modified: str
    conflict_count: int


class MeldFileResponse(ResponseModel):
    path: str
    name: str
    type: Literal["vocabulary", "ontology", "deontic", "inference"]
    size_bytes: int


class ProjectResponse(ResponseModel):
    path: str
    name: str
    loaded_at: str
    meld_files: list[MeldFileResponse]
    domains: list[DomainResponse]


class SourcesResponse(ResponseModel):
    revision: str
    sources: dict[str, str]


class VerdictResponse(ResponseModel):
    decision: Literal["PERMITTED", "FORBIDDEN", "UNDECIDABLE"]
    reason_type: str
    justification_chain: list[str]
    revision: str
    norms_applied: list[str]
    explanation: str
