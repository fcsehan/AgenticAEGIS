"""AEGIS-1201 + Epic 14: Domain Editor Backend API.

REST endpoints for the domain editor frontend.
Provides CRUD operations for domains, guard checking for the test console,
conflict analysis, hierarchy data, .meld import/export,
LLM provider detection, MELD generation, verification, legal docs, and release gate.
"""

from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from aegis.editor.contracts import DomainResponse, ProjectResponse, SourcesResponse, VerdictResponse
from aegis.editor.domain_analysis import analyze_domain
from aegis.editor.domain_model import (
    DomainInfo,
    RuleInfo,
    domain_from_meld,
)
from aegis.editor.legal_doc import LegalDocGenerator
from aegis.editor.llm_provider import LLMClient, LLMProviderInfo, get_all_providers
from aegis.editor.mediation import authorize_editor
from aegis.editor.meld_generator import MeldGenerator, RuleProposal, build_meld_expression
from aegis.editor.release_gate import ReleaseGate, ReleaseState, compute_doc_hash
from aegis.editor.snapshot_verification import canonical_expression, verify_snapshot
from aegis.editor.source_store import SourceStore
from aegis.editor.verification import VerificationPipeline
from aegis.guard.action import Action
from aegis.guard.guard import Guard

router = APIRouter(prefix="/api", tags=["editor"], dependencies=[Depends(authorize_editor)])


# ── In-memory state ──────────────────────────────────────────────


class EditorState:
    """Holds loaded projects and domains."""

    def __init__(self) -> None:
        self.domains: dict[str, DomainInfo] = {}
        self.guards: dict[str, Guard] = {}
        self.project_path: Path | None = None
        self.project_info: dict[str, Any] | None = None
        self.providers: list[LLMProviderInfo] = []
        self.sources: dict[str, SourceStore] = {}
        self.release_states: dict[str, ReleaseState] = {}

    def load_project(self, path: Path) -> dict[str, Any]:
        """Load a project directory containing .meld files."""
        if not path.is_dir():
            raise ValueError(f"Not a directory: {path}")

        path = path.resolve()
        meld_files = sorted(
            p for p in path.rglob("*.meld") if ".aegis-editor" not in p.relative_to(path).parts
        )
        if any(not p.resolve().is_relative_to(path) for p in meld_files):
            raise ValueError("MELD files must stay within the project")
        domains: dict[str, DomainInfo] = {}
        guards: dict[str, Guard] = {}
        sources: dict[str, SourceStore] = {}
        by_dir: dict[Path, list[Path]] = {}
        for mf in meld_files:
            by_dir.setdefault(mf.parent, []).append(mf)
        for domain_dir, domain_melds in by_dir.items():
            relative = domain_dir.relative_to(path).as_posix()
            import base64

            domain_id = (
                "~root"
                if relative == "."
                else relative
                if "/" not in relative and "~" not in relative
                else "~" + base64.urlsafe_b64encode(relative.encode()).decode().rstrip("=")
            )
            if domain_id in sources:
                raise ValueError("Ambiguous domain IDs; rename conflicting source directories")
            source_store = SourceStore(path, domain_id, domain_melds)
            sources[domain_id] = source_store
            try:
                guard = source_store.guard()
                _, revision = source_store.load()
                domain = domain_from_meld(
                    domain_id, domain_dir.name, domain_melds, guard, guard._norms, guard._kb
                )
                from aegis.editor.project_api import read_domain_metadata

                metadata = read_domain_metadata(source_store.directory, domain.name)
                domain.name = metadata["name"]
                domain.description = metadata["description"]
                domain.classification = metadata["classification"]
                domain.status = "Archived" if metadata["archived"] else "Draft"
                governance_path = source_store.directory / "governance.json"
                if governance_path.is_symlink():
                    raise ValueError("Governance symlinks are not supported")
                if domain.status != "Archived" and governance_path.exists():
                    governance_data = json.loads(governance_path.read_text())
                    if any(v["revision"] == revision for v in governance_data.get("versions", [])):
                        domain.status = "Published"
                    elif (governance_data.get("review") or {}).get("revision") == revision:
                        domain.status = "Review"
                domain.revision = revision
                domains[domain_id] = domain
                guards[domain_id] = guard
            except Exception as exc:
                domains[domain_id] = DomainInfo(
                    id=domain_id,
                    name=domain_dir.name,
                    load_error=f"Load failed: {type(exc).__name__}",
                )
        self.project_path = path
        self.domains = domains
        self.guards = guards
        self.sources = sources
        self.release_states.clear()
        self.project_info = {
            "path": str(path),
            "name": path.name,
            "loadedAt": datetime.now(UTC).isoformat(),
            "meldFiles": [
                {
                    "path": str(f.relative_to(path)),
                    "name": f.name,
                    "type": "vocabulary"
                    if "vocab" in f.name.lower()
                    else "ontology"
                    if "ontolog" in f.name.lower()
                    else "deontic",
                    "sizeBytes": f.stat().st_size,
                }
                for f in meld_files
            ],
            "domains": [d.to_dict() for d in domains.values()],
        }

        return self.project_info


# Global state — initialized by the app factory
_state = EditorState()
request_state: ContextVar[EditorState | None] = ContextVar("editor_state", default=None)


def get_state() -> EditorState:
    return request_state.get() or _state


# ── Request/Response models ──────────────────────────────────────


class OpenProjectRequest(BaseModel):
    path: str


class CheckRequest(BaseModel):
    agent: str
    action_type: str = Field(alias="actionType")
    description: str = ""
    parameters: dict[str, str] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class RuleRequest(BaseModel):
    code: str = ""
    agent_role: str = Field(alias="agentRole", default="")
    modality: str = "FORBIDDEN"
    proposition: str = ""
    specificity: int = 0
    defeasible: bool = True

    model_config = {"populate_by_name": True}


class GenerateRequest(BaseModel):
    description: str
    provider_id: str = Field(alias="providerId", default="")
    model_id: str = Field(alias="modelId", default="")
    roles: list[str] = Field(default_factory=list)
    action_types: list[str] = Field(alias="actionTypes", default_factory=list)

    model_config = {"populate_by_name": True}


class RefineRequest(BaseModel):
    proposal: dict[str, Any]
    feedback: str
    provider_id: str = Field(alias="providerId", default="")
    model_id: str = Field(alias="modelId", default="")

    model_config = {"populate_by_name": True}


class VerifyRequest(BaseModel):
    meld_expression: str = Field(alias="meldExpression")
    modality: str = "FORBIDDEN"
    agent_role: str = Field(alias="agentRole", default="*")
    code_of_conduct: str = Field(alias="codeOfConduct", default="")
    action_type: str = Field(alias="actionType", default="")
    proposition_parameters: dict[str, str] = Field(
        alias="propositionParameters",
        default_factory=dict,
    )
    defeasible: bool = True

    model_config = {"populate_by_name": True}


class ReleaseRequest(BaseModel):
    version: str
    message: str = ""

    model_config = {"populate_by_name": True}


# ── Routes ───────────────────────────────────────────────────────


@router.post("/project/open", response_model=ProjectResponse)
async def open_project(body: OpenProjectRequest, request: Request) -> dict[str, Any]:
    """Load a project directory."""
    try:
        path = Path(body.path).resolve()
        workspace = getattr(request.app.state, "workspace", None)
        if workspace is not None and not path.is_relative_to(workspace):
            raise HTTPException(403, "Project is outside configured workspace")
        result = get_state().load_project(path)
        provider_store = getattr(request.app.state, "provider_store", None)
        if provider_store is not None:
            (provider_store.path.parent / "session.json").write_text(
                json.dumps({"project": str(path)}), encoding="utf-8"
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/domains", response_model=list[DomainResponse])
async def list_domains() -> list[dict[str, Any]]:
    return [d.to_dict() for d in get_state().domains.values()]


@router.get("/domains/{domain_id}", response_model=DomainResponse)
async def get_domain(domain_id: str) -> dict[str, Any]:
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")
    return domain.to_dict()


@router.post("/domains", response_model=DomainResponse)
async def create_domain(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """Create a new empty domain."""
    if hasattr(request.app.state, "editor_state"):
        import re

        project_path = get_state().project_path
        if project_path is None:
            raise HTTPException(409, "Open a project first")
        name = str(body.get("name", "")).strip()
        if not name or len(name) > 100:
            raise HTTPException(422, "A domain name is required (maximum 100 characters)")
        domain_id = re.sub(r"[^a-z0-9_-]", "-", name.lower()).strip("-") or "domain"
        target = project_path / domain_id
        if target.exists():
            raise HTTPException(409, "Domain directory already exists")
        target.mkdir()
        try:
            for filename, content in {
                "ontology.meld": "(aegis-schema-version 1)\n(case EditorOntologyMt)\n",
                "action_vocab.meld": "(aegis-schema-version 1)\n(case EditorActionVocabMt)\n",
                "deontic_rules.meld": "(aegis-schema-version 1)\n(case EditorRulesMt)\n",
            }.items():
                (target / filename).write_text(content, encoding="utf-8")
            get_state().load_project(project_path)
        except Exception:
            import shutil

            shutil.rmtree(target)
            raise
        from aegis.editor.project_api import Metadata, save_metadata

        return save_metadata(
            domain_id, Metadata(name=name, description=str(body.get("description", "")))
        )
    domain_id = body.get("id", str(uuid.uuid4())[:8])
    name = body.get("name", domain_id)
    domain = DomainInfo(id=domain_id, name=name, description=body.get("description", ""))
    get_state().domains[domain_id] = domain
    return domain.to_dict()


@router.put("/domains/{domain_id}")
async def update_domain(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Update domain metadata."""
    if domain_id in get_state().sources:
        raise HTTPException(409, "Use revision-bound metadata endpoint")
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")
    if "name" in body:
        domain.name = body["name"]
    if "description" in body:
        domain.description = body["description"]
    if "status" in body:
        raise HTTPException(409, "Status changes require the release workflow")
    return domain.to_dict()


@router.post("/domains/{domain_id}/rules")
async def add_rule(domain_id: str, body: RuleRequest) -> dict[str, Any]:
    """Add a rule to a domain."""
    if domain_id in get_state().sources:
        raise HTTPException(409, "Use revision-bound source-rules endpoint")
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")
    rule = RuleInfo(
        id=str(uuid.uuid4())[:8],
        code=body.code,
        agent_role=body.agent_role,
        modality=body.modality,
        proposition=body.proposition,
        specificity=body.specificity,
        defeasible=body.defeasible,
    )
    domain.rules.append(rule)
    # Update role rule count
    for role in domain.roles:
        if role.name == rule.agent_role:
            role.rule_count += 1
    return rule.to_dict()


@router.delete("/domains/{domain_id}/rules/{rule_id}")
async def delete_rule(domain_id: str, rule_id: str) -> dict[str, str]:
    if domain_id in get_state().sources:
        raise HTTPException(409, "Use revision-bound source-rules endpoint")
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")
    domain.rules = [r for r in domain.rules if r.id != rule_id]
    return {"status": "deleted"}


@router.get("/domains/{domain_id}/validate")
async def validate_domain(domain_id: str) -> dict[str, Any]:
    """Validate all symbols in a domain."""
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")

    guard = get_state().guards.get(domain_id)
    if guard is None:
        raise HTTPException(409, "Load a compiled source domain before validation")
    return analyze_domain(domain, guard)


@router.post("/domains/{domain_id}/check", response_model=VerdictResponse)
async def check_action(domain_id: str, body: CheckRequest) -> dict[str, Any]:
    """Run Guard.check() for the test console."""
    guard = get_state().guards.get(domain_id)
    if guard is None:
        raise HTTPException(
            status_code=400,
            detail=f"Domain {domain_id!r} has no loaded guard (load .meld files first)",
        )

    source_store = get_state().sources.get(domain_id)
    if source_store and source_store.load()[1] != get_state().domains[domain_id].revision:
        raise HTTPException(
            409, "Source files changed externally; reopen the project before testing"
        )

    action = Action(
        action_type=body.action_type,
        agent_id=body.agent,
        proposition=body.parameters,
        context=body.context,
    )
    verdict = guard.check(action)

    return {
        "revision": get_state().domains[domain_id].revision,
        "decision": verdict.decision.value,
        "reasonType": verdict.reason_type.value,
        "justificationChain": list(verdict.justification_chain),
        "normsApplied": list(verdict.norms_applied),
        "explanation": verdict.explain(),
    }


@router.get("/domains/{domain_id}/conflicts")
async def get_conflicts(domain_id: str) -> dict[str, Any]:
    """Get all norm conflicts in a domain."""
    domain = get_state().domains.get(domain_id)
    guard = get_state().guards.get(domain_id)
    if domain is None or guard is None:
        raise HTTPException(404, "Compiled domain not found")
    return analyze_domain(domain, guard)


@router.get("/domains/{domain_id}/hierarchy")
async def get_hierarchy(domain_id: str) -> dict[str, Any]:
    """Get norm hierarchy as a graph structure."""
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Code nodes
    for code in domain.codes:
        nodes.append(
            {
                "id": f"code-{code.id}",
                "type": "code",
                "label": code.name,
                "prevalence": code.prevalence,
            }
        )

    # Rule nodes grouped by role
    for rule in domain.rules:
        node_id = f"rule-{rule.id}"
        nodes.append(
            {
                "id": node_id,
                "type": "rule",
                "label": f"{rule.modality}: {rule.proposition[:40]}",
                "modality": rule.modality,
                "agentRole": rule.agent_role,
            }
        )
        if rule.code:
            edges.append(
                {
                    "source": f"code-{rule.code}",
                    "target": node_id,
                    "type": "membership",
                }
            )

    return {"nodes": nodes, "edges": edges}


@router.get("/domains/{domain_id}/export")
async def export_domain_meld(domain_id: str) -> dict[str, Any]:
    """Export domain as .meld files."""
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")

    source_store = get_state().sources.get(domain_id)
    if source_store is None:
        raise HTTPException(409, "Save a MELD source project before exporting")
    sources, revision = source_store.load()
    return {"revision": revision, "files": sources}


# ── Epic 14: LLM-Assisted MELD Authoring ─────────────────────────


# ── AEGIS-1401: LLM Provider Detection ───────────────────────────


@router.get("/llm/providers")
async def list_providers(request: Request) -> list[dict[str, Any]]:
    """List all detected and configured LLM providers."""
    if hasattr(request.app.state, "provider_store"):
        from aegis.editor.provider_api import provider_info, store

        profiles = store(request).load().profiles
        return [
            {
                **provider_info(p).to_dict(),
                "models": (
                    [{"id": p.model, "name": p.model, "contextLength": None}] if p.model else []
                ),
                "error": "Connection not tested",
            }
            for p in profiles
            if p.enabled
        ]
    if not get_state().providers:
        get_state().providers = get_all_providers()
    return [p.to_dict() for p in get_state().providers]


@router.post("/llm/providers/refresh")
async def refresh_providers(request: Request) -> list[dict[str, Any]]:
    """Re-probe all providers and return updated list."""
    if hasattr(request.app.state, "provider_store"):
        from aegis.editor.provider_api import probe_profile, store

        return [
            await probe_profile(p.id, request) for p in store(request).load().profiles if p.enabled
        ]
    get_state().providers = []
    return await list_providers(request)


def _get_llm_client(provider_id: str, model_id: str) -> LLMClient:
    """Resolve a provider+model into an LLMClient. Raises HTTPException."""
    if not get_state().providers:
        get_state().providers = get_all_providers()
    provider = next((p for p in get_state().providers if p.id == provider_id), None)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id!r} not found")
    if not provider.available:
        raise HTTPException(status_code=400, detail=f"Provider {provider_id!r} is not available")
    return LLMClient(provider, model_id)


# ── AEGIS-1402: MELD Generation ──────────────────────────────────


@router.post("/domains/{domain_id}/generate")
async def generate_rules(domain_id: str, body: GenerateRequest, request: Request) -> dict[str, Any]:
    """Generate rule proposals from natural language description."""
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")

    if hasattr(request.app.state, "provider_store"):
        from aegis.editor.provider_api import configured_client

        client = configured_client(request, body.provider_id, body.model_id)
        settings_revision = request.app.state.provider_store.load().revision
        if (
            settings_revision,
            body.provider_id,
            client.model_id,
        ) not in request.app.state.capabilities:
            raise HTTPException(409, "Verify model tool capability before generating rules")
    else:
        client = _get_llm_client(body.provider_id, body.model_id)
    project_before = get_state().project_path
    revision_before = domain.revision
    generator = MeldGenerator(client, domain)
    proposals = await run_in_threadpool(
        generator.generate,
        body.description,
        roles=body.roles or None,
        action_types=body.action_types or None,
    )

    if (
        get_state().project_path != project_before
        or get_state().domains.get(domain_id) is not domain
        or domain.revision != revision_before
    ):
        raise HTTPException(409, "Project changed during inference; result was not adopted")

    if domain_id in get_state().sources:
        try:
            for proposal in proposals:
                proposal.meld_expression = canonical_expression(
                    proposal, get_state().guards[domain_id]
                )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    # Track generation stats
    rs = get_state().release_states.setdefault(domain_id, ReleaseState())
    rs.provider_id = body.provider_id
    rs.model_id = body.model_id
    rs.rules_generated += len(proposals)

    return {
        "proposals": [p.to_dict() for p in proposals],
        "count": len(proposals),
        "revision": revision_before,
        "inference": {
            "providerId": client.provider_id,
            "modelId": client.model_id,
            "profileRevision": settings_revision
            if hasattr(request.app.state, "provider_store")
            else None,
            "temperature": client._temperature,
            "maxTokens": client._max_tokens,
            "timeout": client._timeout,
        },
    }


@router.post("/domains/{domain_id}/generate/refine")
async def refine_rule(domain_id: str, body: RefineRequest, request: Request) -> dict[str, Any]:
    """Refine a rule proposal based on user feedback."""
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")

    if hasattr(request.app.state, "provider_store"):
        from aegis.editor.provider_api import configured_client

        client = configured_client(request, body.provider_id, body.model_id)
        settings_revision = request.app.state.provider_store.load().revision
        if (
            settings_revision,
            body.provider_id,
            client.model_id,
        ) not in request.app.state.capabilities:
            raise HTTPException(409, "Verify model tool capability before generating rules")
    else:
        client = _get_llm_client(body.provider_id, body.model_id)
    project_before = get_state().project_path
    revision_before = domain.revision
    generator = MeldGenerator(client, domain)

    p = body.proposal
    original = RuleProposal(
        modality=p.get("modality", "FORBIDDEN"),
        agent_role=p.get("agentRole", "*"),
        code_of_conduct=p.get("codeOfConduct", ""),
        action_type=p.get("actionType", ""),
        proposition_parameters=p.get("propositionParameters", {}),
        defeasible=p.get("defeasible", True),
        reasoning=p.get("reasoning", ""),
        natural_language_summary=p.get("naturalLanguageSummary", ""),
    )
    original.meld_expression = build_meld_expression(original)

    refined = await run_in_threadpool(generator.refine_proposal, original, body.feedback)
    if (
        get_state().project_path != project_before
        or get_state().domains.get(domain_id) is not domain
        or domain.revision != revision_before
    ):
        raise HTTPException(409, "Project changed during inference; result was not adopted")
    if domain_id in get_state().sources:
        from aegis.editor.snapshot_verification import canonical_expression

        for proposal in refined:
            proposal.meld_expression = canonical_expression(proposal, get_state().guards[domain_id])
    return {
        "proposals": [r.to_dict() for r in refined],
        "count": len(refined),
        "revision": revision_before,
        "inference": {
            "providerId": client.provider_id,
            "modelId": client.model_id,
            "profileRevision": settings_revision
            if hasattr(request.app.state, "provider_store")
            else None,
            "temperature": client._temperature,
            "maxTokens": client._max_tokens,
            "timeout": client._timeout,
        },
    }


# ── AEGIS-1403: Verification Pipeline ────────────────────────────


@router.post("/domains/{domain_id}/verify")
async def verify_rule(domain_id: str, body: VerifyRequest) -> dict[str, Any]:
    """Run the 4-stage verification pipeline on a rule."""
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")

    proposal = RuleProposal(
        modality=body.modality,
        agent_role=body.agent_role,
        code_of_conduct=body.code_of_conduct,
        action_type=body.action_type,
        proposition_parameters=body.proposition_parameters,
        defeasible=body.defeasible,
        reasoning="",
        natural_language_summary="",
        meld_expression=body.meld_expression,
    )

    if domain_id in get_state().sources:
        sources, revision = get_state().sources[domain_id].load()
        result_dict = verify_snapshot(proposal, get_state().guards[domain_id], sources)
        return {**result_dict, "revision": revision}

    pipeline = VerificationPipeline(domain)
    result = pipeline.verify(proposal)

    # Proposal verification is not a functional test of an accepted domain revision.
    # Never increment release coverage counters for repeated proposal requests.
    return result.to_dict()


# ── AEGIS-1405: Legal Documentation ──────────────────────────────


@router.get("/domains/{domain_id}/legal-doc")
async def get_legal_doc(
    domain_id: str,
    locale: str = Query(default="en", pattern="^en$"),
) -> dict[str, Any]:
    """Generate a legal documentation document for the domain."""
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")

    # Documentation follows the same immutable draft snapshot as tests/export.
    source_store = get_state().sources.get(domain_id)
    if source_store is None:
        meld_source = ""
    else:
        sources, revision = source_store.load()
        if revision != domain.revision:
            raise HTTPException(409, "Source changed; reload the domain")
        meld_source = "\n".join(f";; {name}\n{text}" for name, text in sorted(sources.items()))

    # A document must not claim global resolution from different code names/specificities.
    conflicts: list[dict[str, Any]] = []
    gen = LegalDocGenerator(domain, locale=locale)
    markdown = gen.generate(
        conflicts=conflicts if conflicts else None,
        meld_source=meld_source,
    )

    markdown += (
        "\n\nConflict coverage: run explicit Guard scenarios; "
        "this document is not a global conflict proof.\n"
    )
    doc_hash = compute_doc_hash(markdown)

    # Track legal doc generation
    rs = get_state().release_states.setdefault(domain_id, ReleaseState())
    rs.legal_doc_generated = True
    rs.legal_doc_hash = doc_hash

    return {
        "markdown": markdown,
        "locale": locale,
        "hash": doc_hash,
    }


# ── AEGIS-1406: Release Gate ─────────────────────────────────────


@router.get("/domains/{domain_id}/release/preconditions")
async def get_preconditions(domain_id: str) -> dict[str, Any]:
    """Check all release preconditions for a domain."""
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")

    rs = get_state().release_states.get(domain_id, ReleaseState())
    gate = ReleaseGate(domain, rs)
    preconditions = gate.check_preconditions()

    return {
        "preconditions": [pc.to_dict() for pc in preconditions],
        "canRelease": gate.can_release(),
    }


@router.post("/domains/{domain_id}/release")
async def release_domain(domain_id: str, body: ReleaseRequest) -> dict[str, Any]:
    """Release a domain for production use."""
    domain = get_state().domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")

    project_path = get_state().project_path
    if project_path is None:
        raise HTTPException(status_code=400, detail="No project loaded")

    rs = get_state().release_states.get(domain_id, ReleaseState())
    gate = ReleaseGate(domain, rs)

    if not gate.can_release():
        preconditions = gate.check_preconditions()
        unmet = [pc.id.value for pc in preconditions if not pc.satisfied]
        raise HTTPException(
            status_code=400,
            detail=f"Release preconditions not met: {', '.join(unmet)}",
        )

    from aegis.editor.governance import GovernanceManager

    governance = GovernanceManager(repo_path=project_path)
    output_dir = project_path / domain_id

    result = gate.release(
        governance=governance,
        output_dir=output_dir,
        version=body.version,
        message=body.message,
    )

    return result.to_dict()


class SourceRequest(BaseModel):
    revision: str
    sources: dict[str, str]


@router.get("/domains/{domain_id}/sources", response_model=SourcesResponse)
def get_sources(domain_id: str) -> dict[str, Any]:
    source_store = get_state().sources.get(domain_id)
    if source_store is None:
        raise HTTPException(404, "No source project for this domain")
    sources, revision = source_store.load()
    return {"sources": sources, "revision": revision}


@router.put("/domains/{domain_id}/sources", response_model=DomainResponse)
def save_sources(domain_id: str, body: SourceRequest) -> dict[str, Any]:
    state = get_state()
    source_store = state.sources.get(domain_id)
    if source_store is None:
        raise HTTPException(404, "No source project for this domain")
    try:
        guard, revision = source_store.save(body.sources, body.revision)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, f"MELD compilation failed: {type(exc).__name__}") from exc
    previous = state.domains[domain_id]
    domain = domain_from_meld(
        domain_id, previous.name, source_store.originals, guard, guard._norms, guard._kb
    )
    domain.revision = revision
    domain.description = previous.description
    domain.classification = previous.classification
    domain.status = (
        previous.status
        if revision == previous.revision or previous.status == "Archived"
        else "Draft"
    )
    state.domains[domain_id] = domain
    state.guards[domain_id] = guard
    state.release_states.pop(domain_id, None)
    return domain.to_dict()


@router.get("/project", response_model=ProjectResponse | None)
def current_project() -> dict[str, Any] | None:
    state = get_state()
    if state.project_info is None:
        return None
    return {**state.project_info, "domains": [d.to_dict() for d in state.domains.values()]}


@router.post("/project/close")
def close_project(request: Request) -> dict[str, bool]:
    state = get_state()
    state.project_path = None
    state.project_info = None
    state.domains.clear()
    state.guards.clear()
    state.sources.clear()
    state.release_states.clear()
    provider_store = getattr(request.app.state, "provider_store", None)
    if provider_store:
        (provider_store.path.parent / "session.json").unlink(missing_ok=True)
    return {"closed": True}


class AcceptProposalRequest(VerifyRequest):
    revision: str


@router.post("/domains/{domain_id}/proposals/accept", response_model=DomainResponse)
def accept_proposal(domain_id: str, body: AcceptProposalRequest) -> dict[str, Any]:
    """Explicit adoption into a compiled MELD draft, never a release operation."""
    from aegis.kb.meld_loader import extract_norm, parse_meld

    state = get_state()
    source_store = state.sources.get(domain_id)
    domain = state.domains.get(domain_id)
    guard = state.guards.get(domain_id)
    if source_store is None or domain is None or guard is None:
        raise HTTPException(404, "Load a valid MELD domain first")
    proposal = RuleProposal(
        modality=body.modality,
        agent_role=body.agent_role,
        code_of_conduct=body.code_of_conduct,
        action_type=body.action_type,
        proposition_parameters=body.proposition_parameters,
        defeasible=body.defeasible,
        reasoning="",
        natural_language_summary="",
        meld_expression=body.meld_expression,
    )
    try:
        expected = canonical_expression(proposal, guard)
        assertions = parse_meld(body.meld_expression)
        if len(assertions) != 1 or assertions != parse_meld(expected):
            raise ValueError("Proposal fields and MELD expression disagree")
        norm = extract_norm(assertions[0], "EditorProposalsMt", "<proposal>")
        if norm is None or not guard._registry.is_known(body.action_type):
            raise ValueError("Proposal must reference a known action type")
        sources, revision = source_store.load()
        result = verify_snapshot(proposal, guard, sources)
        if not result["passed"]:
            raise ValueError("Proposal verification failed; inspect the verification stages")
        if revision != body.revision:
            raise ValueError("Domain changed; verify against the current revision")
        if any("(aegis-schema-version 2)" in content for content in sources.values()):
            raise ValueError(
                "Legacy proposal adoption is not supported for schema 2; use MELD sources"
            )
        filename = "EditorProposals.meld"
        current = sources.get(filename, "(aegis-schema-version 1)\n(case EditorProposalsMt)\n")
        if assertions[0] in parse_meld(current):
            return domain.to_dict()
        sources[filename] = current + "\n" + expected + "\n"
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return save_sources(domain_id, SourceRequest(revision=revision, sources=sources))


@router.post("/project/create", response_model=ProjectResponse)
async def create_project(body: OpenProjectRequest, request: Request) -> dict[str, Any]:
    path = Path(body.path).resolve()
    workspace = getattr(request.app.state, "workspace", None)
    if workspace is None or not path.is_relative_to(workspace):
        raise HTTPException(403, "New projects must be inside the configured workspace")
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise HTTPException(409, "Project path already exists; open it instead") from exc
    return await open_project(body, request)
