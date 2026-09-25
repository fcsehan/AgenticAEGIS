"""Tests for AEGIS-2718 — Red-Team CLI plan subcommands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.redteam.cli import main

# ── plan-scenarios ────────────────────────────────────────────────


class TestPlanScenariosCommand:
    def test_all_resisted_exits_zero(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["plan-scenarios"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "Bypass count: 0" in out
        assert "RESISTED" in out

    def test_writes_json_report(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        report_path = tmp_path / "report.json"
        with pytest.raises(SystemExit) as exc:
            main(["plan-scenarios", "--output", str(report_path)])
        assert exc.value.code == 0
        assert report_path.exists()
        payload = json.loads(report_path.read_text())
        assert payload["bypass_count"] == 0
        assert len(payload["outcomes"]) == 6
        assert all(
            o["scenario_id"].startswith("RT-PLAN-")
            for o in payload["outcomes"]
        )

    def test_single_scenario_filter(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["plan-scenarios", "--scenario", "RT-PLAN-03"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        # Only one scenario reported.
        assert out.count("RT-PLAN-") == 1
        assert "RT-PLAN-03" in out

    def test_unknown_scenario_id_exits_two(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["plan-scenarios", "--scenario", "RT-NONE-99"])
        assert exc.value.code == 2


# ── plan-coverage ─────────────────────────────────────────────────


class TestPlanCoverageCommand:
    def test_markdown_format_prints_table(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        main(["plan-coverage", "--format", "markdown"])
        out = capsys.readouterr().out
        assert "# Plan-Scenario Coverage" in out
        assert "| Scenario | Expected" in out
        for sid in ("RT-PLAN-01", "RT-PLAN-02", "RT-PLAN-03",
                    "RT-PLAN-04", "RT-PLAN-05", "RT-PLAN-06"):
            assert sid in out

    def test_json_format_prints_structured(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        main(["plan-coverage", "--format", "json"])
        out = capsys.readouterr().out
        rows = json.loads(out)
        assert len(rows) == 6
        ids = [r["scenario_id"] for r in rows]
        assert ids == [
            "RT-PLAN-01", "RT-PLAN-02", "RT-PLAN-03",
            "RT-PLAN-04", "RT-PLAN-05", "RT-PLAN-06",
        ]


# ── Help ──────────────────────────────────────────────────────────


class TestHelp:
    def test_plan_subcommands_in_help(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        with pytest.raises(SystemExit):
            main(["--help"])
        out = capsys.readouterr().out
        assert "plan-scenarios" in out
        assert "plan-coverage" in out
