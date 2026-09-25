"""Verify proposals against complete MELD sources and the actual action vocabulary."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from aegis.editor.meld_generator import RuleProposal
from aegis.guard.action import Action
from aegis.guard.guard import Guard, _detect_schema_version
from aegis.kb.meld_loader import extract_norm, parse_meld

_ATOM = re.compile(r"^[A-Za-z_?*][A-Za-z0-9_?*:-]*$")
_PREDICATES = {
    "OBLIGATORY": "oughtToDo",
    "FORBIDDEN": "forbiddenToDo",
    "PERMITTED": "permittedToDo",
}


def canonical_expression(proposal: RuleProposal, guard: Guard) -> str:
    """Use declared parameter order, not sorted key/value pairs in a positional term."""
    schema = guard._registry.get_schema(proposal.action_type)
    if schema is None:
        raise ValueError("Unknown action type")
    names = [p.name for p in schema.parameters]
    if set(names) != set(proposal.proposition_parameters):
        raise ValueError("Proposal parameters must match the domain action vocabulary")
    symbols = [proposal.agent_role, proposal.action_type]
    if proposal.code_of_conduct:
        symbols.append(proposal.code_of_conduct)
    if any(not _ATOM.fullmatch(symbol) for symbol in symbols):
        raise ValueError("Invalid role, action or code identifier")
    if proposal.modality not in _PREDICATES:
        raise ValueError("Unknown modality")
    values = []
    for name in names:
        value = proposal.proposition_parameters[name]
        parsed = parse_meld(f"(value {value})")
        if len(parsed) != 1 or len(parsed[0]) != 2 or parsed[0][0] != "value":
            raise ValueError("Each parameter must be exactly one MELD term")
        values.append(value)
    predicate = _PREDICATES[proposal.modality]
    head = proposal.agent_role
    if proposal.code_of_conduct:
        predicate += "-WRT"
        head = f"{proposal.code_of_conduct} {head}"
    terms = " ".join([proposal.action_type, *values])
    expression = f"({predicate} {head} ({terms}))"
    norm = extract_norm(parse_meld(expression)[0], "EditorProposalMt", "<proposal>")
    if norm is None or norm.defeasible != proposal.defeasible:
        raise ValueError("Requested defeasibility is not representable by this MELD predicate")
    return expression


def verify_snapshot(
    proposal: RuleProposal, guard: Guard, sources: dict[str, str]
) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []

    def add(stage: str, status: str, message: str, details: dict[str, Any] | None = None) -> None:
        stages.append(
            {"stage": stage, "status": status, "message": message, "details": details or {}}
        )

    try:
        expression = canonical_expression(proposal, guard)
        if parse_meld(expression) != parse_meld(proposal.meld_expression):
            raise ValueError("Proposal fields and MELD expression disagree")
        add("syntax", "PASS", "One canonical MELD assertion")
        schema = guard._registry.get_schema(proposal.action_type)
        assert schema is not None
        inheritance = guard._inheritance
        if inheritance is None:
            raise ValueError("Schema does not support legacy proposal verification")
        for parameter in schema.parameters:
            value = proposal.proposition_parameters[parameter.name]
            if parameter.type_name != "Thing" and not inheritance.is_instance(
                value, parameter.type_name
            ):
                raise ValueError(f"Unknown or incorrectly typed parameter: {parameter.name}")
        known_agents = {n.agent_pattern for n in guard._norms}
        if (
            proposal.agent_role not in known_agents
            and proposal.agent_role != "*"
            and not inheritance.is_instance(proposal.agent_role, "IntelligentAgent")
        ):
            raise ValueError("Unknown agent role")
        known_codes = {n.code for n in guard._norms}
        known_codes.update(str(f[1]) for f in guard._kb.query(("isa", "?code", "CodeOfConduct")))
        if proposal.code_of_conduct and proposal.code_of_conduct not in known_codes:
            raise ValueError("Unknown code of conduct")
        add(
            "symbol", "PASS", "Role, code and typed action parameters checked against loaded domain"
        )
        with tempfile.TemporaryDirectory(prefix="aegis-proposal-") as temp:
            directory = Path(temp)
            for name, content in sources.items():
                (directory / name).write_text(content, encoding="utf-8")
            paths = sorted(directory.glob("*.meld"))
            if any(_detect_schema_version(p) == 2 for p in paths):
                raise ValueError("Legacy proposals cannot be applied to schema 2")
            extra = directory / "EditorVerificationProposal.meld"
            if extra.exists():
                raise ValueError("Reserved verification filename already exists")
            extra.write_text("(aegis-schema-version 1)\n(case EditorProposalMt)\n" + expression)
            compiled = Guard.from_meld_files([*paths, extra])
            verdict = compiled.check(
                Action(
                    action_type=proposal.action_type,
                    agent_id=proposal.agent_role,
                    proposition=proposal.proposition_parameters,
                )
            )
        conflict = "CONFLICT" in verdict.reason_type.value
        add(
            "conflict",
            "FAIL" if conflict else "PASS",
            "Formal Guard conflict result for the proposal action (not global coverage)",
            {"reasonType": verdict.reason_type.value},
        )
        expected = "FORBIDDEN" if proposal.modality == "FORBIDDEN" else "PERMITTED"
        add(
            "functional",
            "PASS" if verdict.decision.value == expected else "FAIL",
            "Action checked with the complete modified source snapshot",
            {
                "verdict": verdict.decision.value,
                "expected": expected,
                "justification": list(verdict.justification_chain),
            },
        )
    except Exception as exc:
        next_stage = [
            s
            for s in ("syntax", "symbol", "conflict", "functional")
            if s not in {x["stage"] for x in stages}
        ]
        if next_stage:
            add(
                next_stage[0],
                "FAIL",
                str(exc)
                if isinstance(exc, ValueError)
                else f"Verification failed: {type(exc).__name__}",
            )
            for stage in next_stage[1:]:
                add(stage, "SKIP", "Earlier stage failed")
    return {
        "passed": len(stages) == 4 and all(s["status"] == "PASS" for s in stages),
        "stages": stages,
    }
