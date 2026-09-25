"""Tests for AEGIS-1601: Versioned Scenario Library."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.redteam.models import RedTeamScenario
from aegis.redteam.scenario_loader import (
    load_scenario_file,
    load_scenario_library,
    scenario_to_yaml,
)
from aegis.redteam.scenarios import build_default_scenarios


@pytest.fixture
def tmp_scenarios(tmp_path: Path) -> Path:
    return tmp_path / "scenarios"


class TestScenarioRoundTrip:
    def test_python_to_yaml_and_back(self, tmp_path: Path) -> None:
        """All 7 built-in scenarios survive round-trip."""
        for scenario in build_default_scenarios():
            yaml_text = scenario_to_yaml(scenario)
            path = tmp_path / f"{scenario.scenario_id}.yaml"
            path.write_text(yaml_text, encoding="utf-8")

            loaded = load_scenario_file(path)
            assert loaded.scenario_id == scenario.scenario_id
            assert loaded.description == scenario.description
            assert loaded.system_prompt == scenario.system_prompt
            assert loaded.user_prompt == scenario.user_prompt
            assert loaded.tool_names == scenario.tool_names
            assert loaded.max_steps == scenario.max_steps
            assert loaded.attempts == scenario.attempts
            assert loaded.policy.expectation == scenario.policy.expectation

    def test_workspace_files_preserved(self, tmp_path: Path) -> None:
        scenario = build_default_scenarios()[0]
        yaml_text = scenario_to_yaml(scenario)
        path = tmp_path / "test.yaml"
        path.write_text(yaml_text, encoding="utf-8")

        loaded = load_scenario_file(path)
        assert len(loaded.workspace_files) == len(scenario.workspace_files)
        for orig, loaded_wf in zip(scenario.workspace_files, loaded.workspace_files, strict=True):
            assert orig.relative_path == loaded_wf.relative_path
            assert orig.classification == loaded_wf.classification
            assert orig.canary_tokens == loaded_wf.canary_tokens


class TestScenarioLibrary:
    def test_load_with_manifest(self, tmp_path: Path) -> None:
        """Scenarios loaded in manifest order."""
        for name, sid in [("b.yaml", "beta"), ("a.yaml", "alpha")]:
            path = tmp_path / name
            path.write_text(scenario_to_yaml(RedTeamScenario(
                scenario_id=sid,
                description="test",
                system_prompt="test",
                user_prompt="test",
                tool_names=("aegis_check",),
            )), encoding="utf-8")

        manifest = tmp_path / "manifest.yaml"
        manifest.write_text("scenarios:\n  - b.yaml\n  - a.yaml\n", encoding="utf-8")

        scenarios = load_scenario_library(tmp_path)
        assert [s.scenario_id for s in scenarios] == ["beta", "alpha"]

    def test_load_without_manifest(self, tmp_path: Path) -> None:
        """Without manifest, alphabetical order."""
        for name, sid in [("b.yaml", "beta"), ("a.yaml", "alpha")]:
            path = tmp_path / name
            path.write_text(scenario_to_yaml(RedTeamScenario(
                scenario_id=sid,
                description="test",
                system_prompt="test",
                user_prompt="test",
                tool_names=("aegis_check",),
            )), encoding="utf-8")

        scenarios = load_scenario_library(tmp_path)
        assert [s.scenario_id for s in scenarios] == ["alpha", "beta"]


class TestInvalidYAML:
    def test_missing_required_field(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("scenario_id: test\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Missing required field"):
            load_scenario_file(path)

    def test_not_a_mapping(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("- item1\n- item2\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Expected a YAML mapping"):
            load_scenario_file(path)
