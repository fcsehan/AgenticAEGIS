"""Tests for AEGIS-2720 — plan-check / plan-verify / plan-benchmark CLI."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from aegis.cli import main

DEVOPS = Path("aegis/domains/devops")


@pytest.fixture
def devops_domain(tmp_path: Path) -> Path:
    """Copy the DevOps domain into a temp dir so the CLI sees a clean
    glob target without picking up the source-tree filesystem."""
    target = tmp_path / "devops"
    target.mkdir()
    for src in [
        DEVOPS / "DevOpsDomainOntologyMt.meld",
        DEVOPS / "DevOpsActionVocabMt.meld",
        DEVOPS / "DevOpsDeonticRulesMt.meld",
        DEVOPS / "DevOpsPlanNormsMt.meld",
    ]:
        shutil.copy(src, target / src.name)
    return target


def _write_plan(tmp_path: Path, name: str, plan: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(plan), encoding="utf-8")
    return p


def _happy_plan() -> dict:
    return {
        "steps": [
            {"action_type": "buildArtifact", "agent_id": "ciAgent",
             "post_state": {"buildStatus": "success"}},
            {"action_type": "testArtifact", "agent_id": "ciAgent",
             "post_state": {"testStatus": "passed"}},
            {"action_type": "deployArtifact", "agent_id": "ciAgent"},
        ],
    }


# ── plan-check ────────────────────────────────────────────────────


class TestPlanCheckExitCodes:
    def test_permitted_exits_zero(
        self, devops_domain: Path, tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plan_path = _write_plan(tmp_path, "p.json", _happy_plan())
        with pytest.raises(SystemExit) as exc:
            main(["plan-check", str(plan_path), "--domains", str(devops_domain)])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "PERMITTED" in out

    def test_forbidden_exits_one(
        self, devops_domain: Path, tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plan = {"steps": [
            {"action_type": "deployArtifact", "agent_id": "ciAgent"},
            {"action_type": "testArtifact", "agent_id": "ciAgent"},
        ]}
        plan_path = _write_plan(tmp_path, "p.json", plan)
        with pytest.raises(SystemExit) as exc:
            main(["plan-check", str(plan_path), "--domains", str(devops_domain)])
        assert exc.value.code == 1

    def test_undecidable_exits_two(
        self, devops_domain: Path, tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plan = {"steps": [
            {"action_type": "phantomOp", "agent_id": "ciAgent"},
        ]}
        plan_path = _write_plan(tmp_path, "p.json", plan)
        with pytest.raises(SystemExit) as exc:
            main(["plan-check", str(plan_path), "--domains", str(devops_domain)])
        assert exc.value.code == 2

    def test_missing_domains_dir_exits_three(
        self, tmp_path: Path,
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        plan_path = _write_plan(tmp_path, "p.json", _happy_plan())
        with pytest.raises(SystemExit) as exc:
            main(["plan-check", str(plan_path), "--domains", str(empty)])
        assert exc.value.code == 3

    def test_malformed_plan_json_exits_three(
        self, devops_domain: Path, tmp_path: Path,
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not-json{", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            main(["plan-check", str(bad), "--domains", str(devops_domain)])
        assert exc.value.code == 3

    def test_non_object_plan_exits_three(
        self, devops_domain: Path, tmp_path: Path,
    ) -> None:
        bad = _write_plan(tmp_path, "p.json", [1, 2, 3])  # list, not dict
        with pytest.raises(SystemExit) as exc:
            main(["plan-check", str(bad), "--domains", str(devops_domain)])
        assert exc.value.code == 3


class TestPlanCheckExplain:
    def test_explain_dumps_violations(
        self, devops_domain: Path, tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plan = {"steps": [
            {"action_type": "deployArtifact", "agent_id": "ciAgent"},
            {"action_type": "testArtifact", "agent_id": "ciAgent"},
        ]}
        plan_path = _write_plan(tmp_path, "p.json", plan)
        with pytest.raises(SystemExit):
            main([
                "plan-check", str(plan_path),
                "--domains", str(devops_domain),
                "--explain",
            ])
        out = capsys.readouterr().out
        assert "PlanDecision" in out
        assert "Violations" in out
        assert "SEQUENCE_VIOLATION" in out

    def test_explain_lists_per_step_decisions(
        self, devops_domain: Path, tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plan_path = _write_plan(tmp_path, "p.json", _happy_plan())
        with pytest.raises(SystemExit):
            main([
                "plan-check", str(plan_path),
                "--domains", str(devops_domain),
                "--explain",
            ])
        out = capsys.readouterr().out
        assert "Per-step decisions" in out
        assert "buildArtifact" in out
        assert "deployArtifact" in out


# ── plan-verify ───────────────────────────────────────────────────


class TestPlanVerify:
    def test_devops_domain_passes_verifier(
        self, devops_domain: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["plan-verify", str(devops_domain)])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "plan-constraints" in out

    def test_missing_meld_dir_exits_three(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(SystemExit) as exc:
            main(["plan-verify", str(empty)])
        assert exc.value.code == 3


# ── plan-benchmark ────────────────────────────────────────────────


class TestPlanBenchmark:
    def test_runs_iterations_and_prints_stats(
        self, devops_domain: Path, tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plan_path = _write_plan(tmp_path, "p.json", _happy_plan())
        with pytest.raises(SystemExit) as exc:
            main([
                "plan-benchmark", str(plan_path),
                "--domains", str(devops_domain),
                "--iterations", "20",
            ])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "min" in out and "mean" in out and "p95" in out

    def test_zero_iterations_clamped_to_one(
        self, devops_domain: Path, tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plan_path = _write_plan(tmp_path, "p.json", _happy_plan())
        with pytest.raises(SystemExit) as exc:
            main([
                "plan-benchmark", str(plan_path),
                "--domains", str(devops_domain),
                "--iterations", "0",
            ])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "1 iterations" in out


# ── help / parser sanity ──────────────────────────────────────────


class TestParserSanity:
    def test_plan_check_in_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            main(["--help"])
        out = capsys.readouterr().out
        assert "plan-check" in out
        assert "plan-verify" in out
        assert "plan-benchmark" in out
