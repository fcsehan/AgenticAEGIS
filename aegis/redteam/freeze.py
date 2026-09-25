"""AEGIS-1604: Incident-to-Regression Freeze.

Freezes EXPOSED scenarios from a red-team report into versioned YAML
files that become permanent regression tests.
"""

from __future__ import annotations

from pathlib import Path

from aegis.redteam.scenario_loader import scenario_to_yaml


def freeze_from_report(report_path: Path, output_dir: Path) -> list[Path]:
    """Read a JSON report, freeze all EXPOSED scenarios to YAML.

    Returns list of created file paths.
    """
    import json

    raw = json.loads(report_path.read_text(encoding="utf-8"))
    frozen: list[Path] = []

    for scenario_data in raw.get("scenarios", []):
        status = scenario_data.get("status", "")
        if "EXPOSED" not in status:
            continue

        scenario_id = scenario_data.get("scenario_id", "unknown")
        out_path = output_dir / f"frozen_{scenario_id}.yaml"
        # We need the original scenario — reconstruct from report data
        frozen_path = _freeze_scenario_data(scenario_data, out_path)
        if frozen_path:
            frozen.append(frozen_path)

    return frozen


def freeze_single(
    *,
    scenario_id: str,
    description: str,
    system_prompt: str,
    user_prompt: str,
    tool_names: list[str],
    workspace_files: list[dict[str, str]] | None = None,
    policy: dict[str, object] | None = None,
    output_dir: Path,
) -> Path:
    """Freeze a single scenario definition to a YAML file."""
    from aegis.redteam.models import RedTeamScenario, ScenarioPolicy, WorkspaceFile

    ws_objects: list[WorkspaceFile] = []
    for wf in workspace_files or []:
        ws_objects.append(WorkspaceFile(
            relative_path=str(wf.get("relative_path", "")),
            classification=str(wf.get("classification", "public")),
            content=str(wf.get("content", "")),
            description=str(wf.get("description", "")),
            canary_tokens=tuple(wf.get("canary_tokens", ())),
            protected_strings=tuple(wf.get("protected_strings", ())),
        ))

    policy_raw = policy or {}
    scenario = RedTeamScenario(
        scenario_id=scenario_id,
        description=description,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_names=tuple(tool_names),
        workspace_files=tuple(ws_objects),
        policy=ScenarioPolicy(
            expectation=str(policy_raw.get("expectation", "resist")),  # type: ignore[arg-type]
            required_tools=tuple(policy_raw.get("required_tools", ())),  # type: ignore[arg-type]
            forbidden_tools=tuple(policy_raw.get("forbidden_tools", ())),  # type: ignore[arg-type]
            guarded_tools=tuple(policy_raw.get("guarded_tools", ())),  # type: ignore[arg-type]
            notes=str(policy_raw.get("notes", "")),
        ),
        tags=("frozen", "regression"),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"frozen_{scenario_id}.yaml"
    out_path.write_text(scenario_to_yaml(scenario), encoding="utf-8")
    return out_path


def _freeze_scenario_data(scenario_data: dict[str, object], out_path: Path) -> Path | None:
    """Write a scenario dict from a report to a YAML file."""
    from aegis.redteam.models import RedTeamScenario, ScenarioPolicy

    try:
        scenario_id = str(scenario_data.get("scenario_id", "unknown"))
        description = str(scenario_data.get("description", ""))

        policy_raw = scenario_data.get("policy", {})
        if not isinstance(policy_raw, dict):
            policy_raw = {}

        scenario = RedTeamScenario(
            scenario_id=scenario_id,
            description=description,
            system_prompt="",  # Not stored in report
            user_prompt="",  # Not stored in report
            tool_names=tuple(scenario_data.get("tool_names", ())),  # type: ignore[arg-type]
            policy=ScenarioPolicy(
                expectation=str(policy_raw.get("expectation", "resist")),  # type: ignore[arg-type]
                notes=str(policy_raw.get("notes", "")),
            ),
            tags=("frozen", "regression"),
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(scenario_to_yaml(scenario), encoding="utf-8")
        return out_path
    except Exception:
        return None
