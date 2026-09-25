"""Shared pytest fixtures and plugins for AEGIS tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from aegis.guard.action import Action
from aegis.guard.guard import Guard


@pytest.fixture
def meld_path(tmp_path: Path) -> Path:
    """Provide a temporary directory for .meld test files."""
    d = tmp_path / "domains"
    d.mkdir()
    return d


@pytest.fixture
def tmp_audit(tmp_path: Path) -> Path:
    """Provide a temporary directory for audit trail output."""
    d = tmp_path / "audit"
    d.mkdir()
    return d


# ── AEGIS-1102: Scenario Runner pytest plugin ────────────────────


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--scenarios",
        action="store",
        default=None,
        help="Path to YAML scenario directory to run",
    )


def pytest_collect_file(
    parent: pytest.Collector, file_path: Path
) -> pytest.Collector | None:
    """Collect .yaml scenario files as test items."""
    scenarios_opt = parent.config.getoption("--scenarios", default=None)

    if file_path.suffix == ".yaml" and file_path.name.startswith("test_"):
        # If --scenarios is set, only collect from that directory
        if scenarios_opt is not None:
            scenarios_path = Path(scenarios_opt).resolve()
            if not str(file_path.resolve()).startswith(str(scenarios_path)):
                return None
        return ScenarioFile.from_parent(parent, path=file_path)  # type: ignore[return-value]

    return None


class ScenarioFile(pytest.File):
    """Pytest collector for YAML scenario files."""

    def collect(self) -> Any:
        with self.path.open() as f:
            data = yaml.safe_load(f)

        scenario_name = data.get("scenario", self.path.stem)

        for i, step in enumerate(data.get("steps", [])):
            step_name = step.get("name", f"step_{i}")
            yield ScenarioItem.from_parent(
                self,
                name=f"{scenario_name}::{step_name}",
                step=step,
                setup=data.get("setup", {}),
            )


class ScenarioItem(pytest.Item):
    """A single scenario step as a pytest test item."""

    def __init__(
        self,
        name: str,
        parent: pytest.Collector,
        step: dict[str, Any],
        setup: dict[str, Any],
    ) -> None:
        super().__init__(name, parent)
        self._step = step
        self._setup = setup

    def runtest(self) -> None:
        action_data = self._step["action"]
        expected = self._step["expected"]

        # Load the guard from setup
        meld_dir = Path(self._setup.get("meld_dir", ""))
        if not meld_dir.is_absolute():
            # Resolve relative to project root
            project_root = Path(__file__).parent.parent
            meld_dir = project_root / meld_dir

        meld_files = sorted(meld_dir.glob("*.meld"))
        if not meld_files:
            pytest.skip(f"No .meld files found in {meld_dir}")

        prevalence = self._setup.get("code_prevalence")
        guard = Guard.from_meld_files(meld_files, code_prevalence=prevalence)

        action = Action(
            action_type=action_data.get("action_type", ""),
            agent_id=action_data.get("agent_id", ""),
            proposition=action_data.get("proposition", {}),
        )

        verdict = guard.check(action)
        expected_decision = expected["decision"]

        assert verdict.decision.value == expected_decision, (
            f"Expected {expected_decision}, got {verdict.decision.value}\n"
            f"  Action: {action.action_type} by {action.agent_id}\n"
            f"  Justification: {verdict.justification_chain}"
        )

    def repr_failure(self, excinfo: pytest.ExceptionInfo[BaseException]) -> str:
        return str(excinfo.value)

    def reportinfo(self) -> tuple[Path, int | None, str]:
        return self.path, None, self.name


# Network/model-dependent tests are explicit opt-in in the public repository.
collect_ignore = [] if os.environ.get("AEGIS_LIVE_LLM") == "1" else [
    "test_e2e_llm.py",
    "editor/test_authoring_e2e.py",
    "redteam/test_live_pipeline.py",
]
