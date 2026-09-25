"""Tests for AEGIS-1604: Incident-to-Regression Freeze."""

from __future__ import annotations

import json
from pathlib import Path

from aegis.redteam.freeze import freeze_from_report, freeze_single
from aegis.redteam.scenario_loader import load_scenario_file


class TestFreezeFromReport:
    def test_freeze_exposed_only(self, tmp_path: Path) -> None:
        report = {
            "scenarios": [
                {
                    "scenario_id": "exposed_one",
                    "description": "An exposed scenario",
                    "status": "EXPOSED",
                    "expectation": "resist",
                    "tool_names": ["aegis_check"],
                    "attempts": [],
                },
                {
                    "scenario_id": "resisted_one",
                    "description": "A resisted scenario",
                    "status": "RESISTED",
                    "expectation": "resist",
                    "attempts": [],
                },
            ]
        }
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        output_dir = tmp_path / "frozen"
        frozen = freeze_from_report(report_path, output_dir)

        assert len(frozen) == 1
        assert "exposed_one" in frozen[0].name

    def test_frozen_file_is_loadable(self, tmp_path: Path) -> None:
        report = {
            "scenarios": [
                {
                    "scenario_id": "test_freeze",
                    "description": "Freezable scenario",
                    "status": "EXPOSED",
                    "expectation": "resist",
                    "tool_names": ["aegis_check"],
                    "attempts": [],
                },
            ]
        }
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        output_dir = tmp_path / "frozen"
        frozen = freeze_from_report(report_path, output_dir)

        loaded = load_scenario_file(frozen[0])
        assert loaded.scenario_id == "test_freeze"
        assert "frozen" in loaded.tags


class TestFreezeSingle:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = freeze_single(
            scenario_id="single_test",
            description="A single frozen scenario",
            system_prompt="System prompt",
            user_prompt="User prompt",
            tool_names=["aegis_check", "read_workspace_file"],
            output_dir=tmp_path,
        )
        assert path.exists()
        loaded = load_scenario_file(path)
        assert loaded.scenario_id == "single_test"
        assert loaded.tool_names == ("aegis_check", "read_workspace_file")
