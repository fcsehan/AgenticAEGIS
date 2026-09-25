"""Scoped diagnostics from the real Guard; never a second conflict resolver."""

from __future__ import annotations

from typing import Any

from aegis.editor.domain_model import DomainInfo, RuleInfo
from aegis.editor.plan_constraint_verification import verify_plan_constraints
from aegis.guard.action import Action
from aegis.guard.guard import Guard


def analyze_domain(domain: DomainInfo, guard: Guard) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    tested: set[tuple[str, tuple[Any, ...]]] = set()
    skipped = 0
    for norm in guard._norms:
        rule_id = RuleInfo.from_norm(norm).id
        if not norm.proposition or not isinstance(norm.proposition[0], str):
            skipped += 1
            continue
        schema = guard._registry.get_schema(norm.proposition[0])
        if schema is None:
            issues.append(
                {
                    "id": f"action-{rule_id}",
                    "severity": "warning",
                    "ruleId": rule_id,
                    "message": "Norm does not map to a declared action type; inspect MELD scope",
                }
            )
            skipped += 1
            continue
        values = norm.proposition[1:]
        if len(values) != len(schema.parameters):
            issues.append(
                {
                    "id": f"arity-{rule_id}",
                    "severity": "error",
                    "ruleId": rule_id,
                    "message": "Norm parameter count differs from the action vocabulary",
                }
            )
            skipped += 1
            continue
        if any(isinstance(v, tuple) or isinstance(v, str) and v.startswith("?") for v in values):
            skipped += 1
            continue
        inheritance = guard._inheritance
        for parameter, value in zip(schema.parameters, values, strict=True):
            if (
                parameter.type_name != "Thing"
                and inheritance is not None
                and not inheritance.is_instance(str(value), parameter.type_name)
            ):
                issues.append(
                    {
                        "id": f"type-{rule_id}-{parameter.name}",
                        "severity": "error",
                        "ruleId": rule_id,
                        "message": f"Unknown or mistyped {parameter.name}: {value}",
                    }
                )
        agents = (
            [r.name for r in domain.roles] if norm.agent_pattern == "*" else [norm.agent_pattern]
        )
        for agent in agents:
            key = (agent, norm.proposition)
            if key in tested:
                continue
            tested.add(key)
            verdict = guard.check(
                Action(
                    action_type=schema.name,
                    agent_id=agent,
                    proposition={p.name: v for p, v in zip(schema.parameters, values, strict=True)},
                )
            )
            if "CONFLICT" in verdict.reason_type.value:
                conflict = {
                    "ruleId": rule_id,
                    "agent": agent,
                    "actionType": schema.name,
                    "resolved": False,
                    "decision": verdict.decision.value,
                    "reasonType": verdict.reason_type.value,
                    "justificationChain": list(verdict.justification_chain),
                }
                conflicts.append(conflict)
                issues.append(
                    {
                        "id": f"conflict-{rule_id}",
                        "severity": "error",
                        "ruleId": rule_id,
                        "message": f"Guard reports {verdict.reason_type.value} for {schema.name}",
                    }
                )
    plan_diagnostics = None
    if guard._module is not None and guard._module.plan_constraints:
        plan_diagnostics = verify_plan_constraints(
            guard._module.plan_constraints, guard._registry, guard._norms
        ).to_dict()
        for stage in plan_diagnostics["stages"]:
            if stage["status"] == "FAIL":
                issues.append(
                    {
                        "id": f"plan-{stage['stage']}",
                        "severity": "error",
                        "message": stage["message"],
                    }
                )
    if skipped or not guard._norms:
        issues.append(
            {
                "id": "partial-coverage",
                "severity": "warning",
                "message": (
                    "Diagnostics cover concrete legacy action instances only. "
                    "Use saved action/plan scenarios for other constructs."
                ),
            }
        )
    return {
        "revision": domain.revision,
        "valid": not any(i["severity"] == "error" for i in issues),
        "issues": issues,
        "conflicts": conflicts,
        "ruleCount": len(domain.rules),
        "roleCount": len(domain.roles),
        "testedActionInstances": len(tested),
        "skippedNorms": skipped,
        "coverage": "concrete-action-instances",
        "planDiagnostics": plan_diagnostics,
    }
