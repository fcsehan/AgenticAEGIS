"""AEGIS-1601: Versioned Scenario Library — YAML loader.

Loads red-team scenarios from YAML files, enabling versioned,
auditable scenario definitions without code changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import RedTeamScenario, ScenarioPolicy, WorkspaceFile


def load_scenario_file(path: Path) -> RedTeamScenario:
    """Load a single scenario from a YAML file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a YAML mapping in {path}, got {type(raw).__name__}")
    return _parse_scenario(raw, source=str(path))


def load_scenario_library(directory: Path) -> list[RedTeamScenario]:
    """Load all scenarios from a directory.

    If a ``manifest.yaml`` exists, scenarios are loaded in manifest order.
    Otherwise, all ``*.yaml`` files (except ``manifest.yaml``) are loaded
    in alphabetical order.
    """
    manifest_path = directory / "manifest.yaml"
    if manifest_path.exists():
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or "scenarios" not in manifest:
            raise ValueError(f"manifest.yaml must contain a 'scenarios' key: {manifest_path}")
        files = [directory / name for name in manifest["scenarios"]]
    else:
        files = sorted(
            f for f in directory.glob("*.yaml")
            if f.name != "manifest.yaml"
        )

    scenarios: list[RedTeamScenario] = []
    for f in files:
        if not f.exists():
            raise FileNotFoundError(f"Scenario file not found: {f}")
        scenarios.append(load_scenario_file(f))
    return scenarios


def scenario_to_yaml(scenario: RedTeamScenario) -> str:
    """Serialize a :class:`RedTeamScenario` to YAML text."""
    data: dict[str, Any] = {
        "scenario_id": scenario.scenario_id,
        "description": scenario.description,
        "system_prompt": scenario.system_prompt,
        "user_prompt": scenario.user_prompt,
        "tool_names": list(scenario.tool_names),
        "max_steps": scenario.max_steps,
        "attempts": scenario.attempts,
    }
    if scenario.tags:
        data["tags"] = list(scenario.tags)

    # Policy
    policy = scenario.policy
    policy_data: dict[str, Any] = {"expectation": policy.expectation}
    for field_name in (
        "required_tools", "forbidden_tools", "guarded_tools",
        "forbidden_canaries", "required_final_substrings",
        "forbidden_final_substrings",
    ):
        val = getattr(policy, field_name)
        if val:
            policy_data[field_name] = list(val)
    if policy.notes:
        policy_data["notes"] = policy.notes
    data["policy"] = policy_data

    # Workspace files
    if scenario.workspace_files:
        ws_list: list[dict[str, Any]] = []
        for wf in scenario.workspace_files:
            ws: dict[str, Any] = {
                "relative_path": wf.relative_path,
                "classification": wf.classification,
                "content": wf.content,
            }
            if wf.description:
                ws["description"] = wf.description
            if wf.canary_tokens:
                ws["canary_tokens"] = list(wf.canary_tokens)
            if wf.protected_strings:
                ws["protected_strings"] = list(wf.protected_strings)
            ws_list.append(ws)
        data["workspace_files"] = ws_list

    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ── Internal parsing ─────────────────────────────────────────


def _parse_scenario(raw: dict[str, Any], *, source: str = "") -> RedTeamScenario:
    """Parse a raw dict into a RedTeamScenario."""
    required = ("scenario_id", "description", "system_prompt", "user_prompt", "tool_names")
    for key in required:
        if key not in raw:
            raise ValueError(f"Missing required field {key!r} in {source}")

    policy_raw = raw.get("policy", {})
    policy = ScenarioPolicy(
        expectation=policy_raw.get("expectation", "resist"),
        required_tools=tuple(policy_raw.get("required_tools", ())),
        forbidden_tools=tuple(policy_raw.get("forbidden_tools", ())),
        guarded_tools=tuple(policy_raw.get("guarded_tools", ())),
        forbidden_canaries=tuple(policy_raw.get("forbidden_canaries", ())),
        required_final_substrings=tuple(policy_raw.get("required_final_substrings", ())),
        forbidden_final_substrings=tuple(policy_raw.get("forbidden_final_substrings", ())),
        notes=policy_raw.get("notes", ""),
    )

    workspace_files: list[WorkspaceFile] = []
    for wf_raw in raw.get("workspace_files", []):
        workspace_files.append(WorkspaceFile(
            relative_path=wf_raw["relative_path"],
            classification=wf_raw["classification"],
            content=wf_raw["content"],
            description=wf_raw.get("description", ""),
            canary_tokens=tuple(wf_raw.get("canary_tokens", ())),
            protected_strings=tuple(wf_raw.get("protected_strings", ())),
        ))

    return RedTeamScenario(
        scenario_id=raw["scenario_id"],
        description=raw["description"],
        system_prompt=raw["system_prompt"],
        user_prompt=raw["user_prompt"],
        tool_names=tuple(raw["tool_names"]),
        workspace_files=tuple(workspace_files),
        policy=policy,
        max_steps=raw.get("max_steps", 6),
        attempts=raw.get("attempts", 2),
        tags=tuple(raw.get("tags", ())),
    )
