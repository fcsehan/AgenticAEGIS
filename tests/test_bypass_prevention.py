"""AEGIS-1108: Guard Bypass Prevention Audit.

Architectural verification via AST analysis that no code path executes
actions without Guard.check() (Invariant I5).

Verifies that:
1. ActionExecutor.execute() always calls guard.check()
2. No other module imports and calls action executors directly
3. The only path to action execution is through the Guard
"""

from __future__ import annotations

import ast
from pathlib import Path

AEGIS_SRC = Path(__file__).parent.parent / "aegis"


class TestBypassPrevention:
    def test_executor_always_calls_guard_check(self) -> None:
        """ActionExecutor.execute() must call self._guard.check()."""
        executor_path = AEGIS_SRC / "api" / "executor.py"
        tree = ast.parse(executor_path.read_text())

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "execute":
                source = ast.dump(node)
                assert "guard" in source.lower() and "check" in source.lower(), (
                    "execute() must call guard.check()"
                )

    def test_no_direct_executor_calls_outside_api(self) -> None:
        """No module outside aegis/api/ and aegis/cli.py should call executor functions directly."""
        api_dir = AEGIS_SRC / "api"
        # cli.py and orchestrator/ are legitimate integration layers
        # that wire the executor into the full stack
        exempt = {AEGIS_SRC / "cli.py", *(AEGIS_SRC / "orchestrator").rglob("*.py")}
        for py_file in AEGIS_SRC.rglob("*.py"):
            if api_dir in py_file.parents or py_file.parent == api_dir:
                continue
            if py_file.name == "__init__.py":
                continue
            if py_file in exempt:
                continue

            content = py_file.read_text()
            # No file outside api/ should import ActionExecutor type alias
            # and call it directly (the callable type, not the class)
            assert "ActionExecutor(" not in content or "api" in str(py_file), (
                f"{py_file} appears to directly instantiate ActionExecutor"
            )

    def test_guard_check_is_only_verdict_source(self) -> None:
        """Only Guard.check() and test code should create Verdict instances.

        Allow-list contains modules that live inside the guard layer and
        whose explicit purpose is to construct Verdicts on behalf of
        Guard.check():

        - ``guard.py``      — Guard.check() entry point.
        - ``pipeline.py``   — EvaluationPipeline, called by Guard.check().
        - ``verdict.py``    — the dataclass itself (factory helpers).
        - ``executor.py``   — guard-side action executor wrapper.
        - ``ddic_belief_state_adapter.py`` — translates DDICBeliefState into Verdict
          for the DDIC v2 path; used only by the pipeline. Added 2026-05-08
          per AEGIS-2309 cleanup of roadmap finding 2.9.
        """
        guard_related = {
            "guard.py",
            "pipeline.py",
            "ddic_pipeline.py",
            "verdict.py",
            "executor.py",
            "ddic_belief_state_adapter.py",
            # Epic 33: User-Confirmation-Loop gate emits Verdicts when
            # a confirmation is rejected or times out. The gate is part
            # of the orchestrator/guard surface, not an external caller.
            "confirmation_gate.py",
            # Epic 27: PlanPipeline emits a placeholder UNDECIDABLE
            # Verdict for D-007 limit / module-not-available short-
            # circuit cases. The pipeline is part of the Guard surface,
            # not an external caller.
            "plan_pipeline.py",
        }
        for py_file in AEGIS_SRC.rglob("*.py"):
            if py_file.name in guard_related:
                continue
            if py_file.name == "__init__.py":
                continue
            if "test" in str(py_file):
                continue

            content = py_file.read_text()
            # Files outside the guard package should not construct Verdicts
            # (they should receive them from guard.check())
            if "Verdict(" in content:
                # Allow imports/type hints, but not construction
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        func = node.func
                        if isinstance(func, ast.Name) and func.id == "Verdict":
                            raise AssertionError(
                                f"{py_file} constructs Verdict directly — "
                                f"only Guard should create Verdicts"
                            )
