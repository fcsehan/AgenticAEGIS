"""AEGIS-1201: Domain Model for the Editor.

The internal representation of a domain as the editor sees it:
roles, obligation types, codes of conduct, and norm rules.
Bridges between the .meld-loaded KB/norms and the frontend JSON API.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aegis.deontic.norm_frame import NormFrame
from aegis.guard.guard import Guard
from aegis.kb.knowledge_base import KnowledgeBase


@dataclass
class Role:
    """An agent role in the domain."""

    id: str
    name: str
    description: str = ""
    rule_count: int = 0
    obligation_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "ruleCount": self.rule_count,
            "obligationType": self.obligation_type,
        }


@dataclass
class ObligationType:
    """An obligation category (e.g. J2 Intelligence)."""

    id: str
    name: str
    description: str = ""
    parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parentId": self.parent_id,
            "children": [],
        }


@dataclass
class CodeOfConductInfo:
    """A code of conduct with prevalence."""

    id: str
    name: str
    prevalence: int = 0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "prevalence": self.prevalence,
            "description": self.description,
        }


@dataclass
class RuleInfo:
    """A deontic rule as the editor presents it."""

    id: str
    code: str
    agent_role: str
    modality: str
    proposition: str
    specificity: int = 0
    defeasible: bool = True
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "agentRole": self.agent_role,
            "modality": self.modality,
            "proposition": self.proposition,
            "specificity": self.specificity,
            "defeasible": self.defeasible,
            "source": self.source,
        }

    @classmethod
    def from_norm(cls, norm: NormFrame) -> RuleInfo:
        return cls(
            id=hashlib.sha256(Path(norm.source).name.encode()).hexdigest()[:16],
            code=norm.code,
            agent_role=norm.agent_pattern,
            modality=norm.modality.value,
            proposition=" ".join(str(p) for p in norm.proposition),
            specificity=norm.specificity,
            defeasible=norm.defeasible,
            source=norm.source,
        )


@dataclass
class DomainInfo:
    """Complete domain representation for the editor."""

    id: str
    name: str
    description: str = ""
    status: str = "Draft"
    classification: str = "confidentialData"
    roles: list[Role] = field(default_factory=list)
    obligation_types: list[ObligationType] = field(default_factory=list)
    codes: list[CodeOfConductInfo] = field(default_factory=list)
    rules: list[RuleInfo] = field(default_factory=list)
    meld_files: list[str] = field(default_factory=list)
    code_prevalence: list[str] = field(default_factory=list)
    action_types: list[str] = field(default_factory=list)
    action_schemas: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    revision: str = ""
    load_error: str = ""
    last_modified: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "classification": self.classification,
            "roles": [r.to_dict() for r in self.roles],
            "obligationTypes": [o.to_dict() for o in self.obligation_types],
            "codes": [c.to_dict() for c in self.codes],
            "rules": [r.to_dict() for r in self.rules],
            "meldFiles": self.meld_files,
            "revision": self.revision,
            "codePrevalence": self.code_prevalence,
            "actionTypes": self.action_types,
            "actionSchemas": self.action_schemas,
            "loadError": self.load_error,
            "compileStatus": "failed"
            if self.load_error
            else "ready"
            if self.revision
            else "uncompiled",
            "lastModified": self.last_modified,
            "conflictCount": 0,
        }


def domain_from_meld(
    domain_id: str,
    name: str,
    meld_paths: list[Path],
    guard: Guard,
    norms: list[NormFrame],
    kb: KnowledgeBase,
) -> DomainInfo:
    """Build a DomainInfo from loaded .meld data."""
    # Extract roles from KB
    roles: list[Role] = []
    role_names: set[str] = set()
    for norm in norms:
        if norm.agent_pattern and norm.agent_pattern != "*":
            role_names.add(norm.agent_pattern)
    for fact in kb.query(("isa", "?agent", "?collection")):
        if (
            isinstance(fact[1], str)
            and isinstance(fact[2], str)
            and (
                fact[2] == "IntelligentAgent"
                or (
                    guard._inheritance is not None
                    and guard._inheritance.is_subtype(fact[2], "IntelligentAgent")
                )
            )
        ):
            role_names.add(fact[1])
    for rn in sorted(role_names):
        count = sum(1 for n in norms if n.agent_pattern == rn)
        roles.append(Role(id=rn, name=rn, rule_count=count, description=_description(kb, rn)))

    # Extract codes
    code_names: set[str] = set()
    for norm in norms:
        if norm.code:
            code_names.add(norm.code)
    code_names.update(str(f[1]) for f in kb.query(("isa", "?code", "CodeOfConduct")))
    codes = [
        CodeOfConductInfo(id=cn, name=cn, description=_description(kb, cn))
        for cn in sorted(code_names)
    ]
    obligation_types = []
    for fact in kb.query(("isa", "?type", "ObligationType")):
        name = str(fact[1])
        parents = kb.query(("genls", name, "?parent"))
        obligation_types.append(
            ObligationType(
                id=name,
                name=name,
                description=_description(kb, name),
                parent_id=str(parents[0][2]) if parents else None,
            )
        )

    obligation_names = {o.name for o in obligation_types}
    for role in roles:
        matching = [
            str(f[2])
            for f in kb.query(("isa", role.name, "?type"))
            if str(f[2]) in obligation_names
        ]
        role.obligation_type = matching[0] if len(matching) == 1 else None

    # Convert norms to rules
    rules = [RuleInfo.from_norm(n) for n in norms]

    return DomainInfo(
        id=domain_id,
        name=name,
        roles=roles,
        codes=codes,
        obligation_types=obligation_types,
        rules=rules,
        meld_files=[str(p.name) for p in meld_paths],
        code_prevalence=list(guard._module.code_prevalence) if guard._module else [],
        action_types=guard._registry.action_types,
        action_schemas={
            name: [{"name": p.name, "type": p.type_name} for p in schema.parameters]
            for name in guard._registry.action_types
            if (schema := guard._registry.get_schema(name)) is not None
        },
    )


def _description(kb: KnowledgeBase, name: str) -> str:
    comments = kb.query(("comment", name, "?text"))
    return str(comments[-1][2]) if comments else ""
