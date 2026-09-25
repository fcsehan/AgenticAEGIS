"""AEGIS-2721 (Epic 27) — DevOps E2E pipeline test.

End-to-end exercise of the full Plan-Level Governance stack on the
DevOps reference domain:

  domain → MeldLoader → DDICModule → Guard
  Plan-JSON → Plan → PlanPipeline → PlanVerdict
  Permitted → PlanActionExecutor → step executors with token validation

Combines a happy-path execution with the six adversarial scenarios
from the epic spec (sequence inversion, aggregate overflow, force
push, precondition missing, rollback late, empty plan), each loaded
from a JSON fixture.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from aegis.api.plan_executor import PlanActionExecutor
from aegis.cli import _plan_from_json
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.plan import Plan, ViolationType
from aegis.guard.verdict import PlanDecision

DEVOPS = Path("aegis/domains/devops")
FIXTURES = Path("tests/fixtures/devops_plans")


@pytest.fixture(scope="module")
def devops_guard() -> Guard:
    return Guard.from_meld_files([
        DEVOPS / "DevOpsDomainOntologyMt.meld",
        DEVOPS / "DevOpsActionVocabMt.meld",
        DEVOPS / "DevOpsDeonticRulesMt.meld",
        DEVOPS / "DevOpsPlanNormsMt.meld",
    ])


def _load_fixture(name: str) -> Plan:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    plan = _plan_from_json(raw)
    assert isinstance(plan, Plan)
    return plan


def _executor(guard: Guard) -> tuple[PlanActionExecutor, list[str]]:
    """Build a PlanActionExecutor with stub step-executors for every
    DevOps action type. Returns the executor and an exec-log."""
    log: list[str] = []
    plan_exec = PlanActionExecutor(guard)
    for action_type in (
        "buildArtifact", "testArtifact", "deployArtifact",
        "emergencyRollback", "requestApproval", "reportIncident",
        "modifySensitiveConfig", "forceModifyRepository",
        "readFile", "modifyFile", "deleteFile", "executeCommand",
        "executeRemoteCode",
    ):
        plan_exec.register(
            action_type,
            lambda a, log=log: log.append(a.action_type) or "ok",
        )
    return plan_exec, log


# ── 1. Happy path E2E ─────────────────────────────────────────────


class TestHappyPathE2E:
    def test_plan_check_executable(self, devops_guard: Guard) -> None:
        plan = _load_fixture("01_happy_path.json")
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.PERMITTED

    def test_executor_runs_all_steps(self, devops_guard: Guard) -> None:
        plan_exec, log = _executor(devops_guard)
        plan = _load_fixture("01_happy_path.json")
        result = plan_exec.execute_plan(plan)
        assert result.all_steps_executed
        assert log == ["buildArtifact", "testArtifact", "deployArtifact"]
        assert len(result.executed_step_records) == 3
        assert all(r.executed for r in result.executed_step_records)

    def test_executor_returns_token_id(self, devops_guard: Guard) -> None:
        plan_exec, _ = _executor(devops_guard)
        plan = _load_fixture("01_happy_path.json")
        result = plan_exec.execute_plan(plan)
        assert result.plan_token_id != ""


# ── 2. Adversarial: sequence inversion ────────────────────────────


class TestAdversarialSequenceInversion:
    def test_blocked_at_plan_check(self, devops_guard: Guard) -> None:
        plan = _load_fixture("02_sequence_inversion.json")
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert any(
            v.violation_type == ViolationType.SEQUENCE_VIOLATION
            for v in verdict.violations
        )

    def test_executor_does_not_run_steps(self, devops_guard: Guard) -> None:
        plan_exec, log = _executor(devops_guard)
        plan = _load_fixture("02_sequence_inversion.json")
        result = plan_exec.execute_plan(plan)
        assert result.plan_verdict.plan_decision == PlanDecision.FORBIDDEN
        assert log == []
        assert result.executed_step_records == ()


# ── 3. Adversarial: aggregate overflow ────────────────────────────


class TestAdversarialAggregate:
    def test_blocked(self, devops_guard: Guard) -> None:
        plan = _load_fixture("03_aggregate_overflow.json")
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert any(
            v.violation_type == ViolationType.AGGREGATE_VIOLATION
            for v in verdict.violations
        )

    def test_executor_does_not_run(self, devops_guard: Guard) -> None:
        plan_exec, log = _executor(devops_guard)
        plan = _load_fixture("03_aggregate_overflow.json")
        plan_exec.execute_plan(plan)
        assert log == []


# ── 4. Adversarial: force-push ────────────────────────────────────


class TestAdversarialForceModify:
    def test_blocked(self, devops_guard: Guard) -> None:
        plan = _load_fixture("04_force_modify.json")
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        # forbid-aggregate-0 triggers AGGREGATE_VIOLATION.
        assert any(
            v.violation_type == ViolationType.AGGREGATE_VIOLATION
            for v in verdict.violations
        )


# ── 5. Adversarial: precondition missing ──────────────────────────


class TestAdversarialPrecondition:
    def test_blocked(self, devops_guard: Guard) -> None:
        plan = _load_fixture("05_precondition_missing.json")
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert any(
            v.violation_type == ViolationType.PRECONDITION_VIOLATION
            for v in verdict.violations
        )


# ── 6. Adversarial: rollback late ─────────────────────────────────


class TestAdversarialRollbackLate:
    def test_blocked_with_timing_violation(self, devops_guard: Guard) -> None:
        plan = _load_fixture("06_rollback_late.json")
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert any(
            v.violation_type == ViolationType.TIMING_VIOLATION
            for v in verdict.violations
        )


# ── 7. Adversarial: empty plan ────────────────────────────────────


class TestAdversarialEmpty:
    def test_blocked(self, devops_guard: Guard) -> None:
        plan = _load_fixture("07_empty.json")
        verdict = devops_guard.plan_check(plan)
        assert verdict.plan_decision == PlanDecision.FORBIDDEN
        assert any(
            v.violation_type == ViolationType.EMPTY_PLAN
            for v in verdict.violations
        )


# ── 8. Smuggling: clean steps then a forbidden one ────────────────


class TestSmuggling:
    def test_dangerous_step_blocks_whole_plan(
        self, devops_guard: Guard,
    ) -> None:
        """Three benign reads then executeRemoteCode at the end —
        the plan-pipeline catches this even though every read is
        individually fine."""
        plan = _load_fixture("10_smuggling_clean_then_danger.json")
        verdict = devops_guard.plan_check(plan)
        # forbid-aggregate-0 on executeRemoteCode triggers AGGREGATE.
        assert verdict.plan_decision == PlanDecision.FORBIDDEN

    def test_executor_runs_no_steps(self, devops_guard: Guard) -> None:
        plan_exec, log = _executor(devops_guard)
        plan = _load_fixture("10_smuggling_clean_then_danger.json")
        plan_exec.execute_plan(plan)
        assert log == []


# ── 9. Backward-compat: single-action plan ────────────────────────


class TestSingleActionBackwardCompat:
    def test_single_action_round_trip(self, devops_guard: Guard) -> None:
        plan = _load_fixture("09_single_action_compat.json")
        plan_verdict = devops_guard.plan_check(plan)
        action_verdict = devops_guard.check(plan.steps[0].action)
        assert (
            plan_verdict.per_step_verdicts[0].decision
            == action_verdict.decision
        )


# ── 10. Performance: 20-step realistic plan ──────────────────────


class TestRealisticPipelinePerformance:
    def test_twenty_step_plan_under_100_ms(
        self, devops_guard: Guard,
    ) -> None:
        """AEGIS-2721 acceptance: realistic 20-step plan must finish
        plan_check in under 100 ms wall-clock on a developer laptop.
        We measure with a small warmup + best-of-3 to dampen jitter."""
        plan = _load_fixture("08_realistic_20_step.json")
        # Warmup so JIT-style first-call costs (logging, lazy imports)
        # don't pollute the measurement.
        for _ in range(3):
            devops_guard.plan_check(plan)
        samples: list[float] = []
        for _ in range(5):
            t0 = time.perf_counter()
            verdict = devops_guard.plan_check(plan)
            samples.append((time.perf_counter() - t0) * 1000.0)
        best = min(samples)
        assert best < 100.0, (
            f"20-step plan_check took {best:.2f} ms (budget 100 ms). "
            f"Samples: {samples}"
        )
        assert verdict.plan_decision in {
            PlanDecision.PERMITTED,
            PlanDecision.FORBIDDEN,
            PlanDecision.UNDECIDABLE,
        }


# ── 11. Executor runtime error ────────────────────────────────────


class TestExecutorRuntimeError:
    def test_runtime_error_aborts_plan(
        self, devops_guard: Guard,
    ) -> None:
        log: list[str] = []
        plan_exec = PlanActionExecutor(devops_guard)

        def boom(action: Action) -> None:
            log.append(action.action_type)
            raise RuntimeError("simulated step failure")

        plan_exec.register("buildArtifact", boom)
        plan_exec.register("testArtifact", lambda a: log.append("test") or "ok")
        plan_exec.register("deployArtifact", lambda a: log.append("deploy") or "ok")
        plan = _load_fixture("01_happy_path.json")
        result = plan_exec.execute_plan(plan)
        assert result.aborted
        assert "executor_error" in result.abort_reason
        # Step 0 attempted, steps 1-2 NOT executed.
        assert log == ["buildArtifact"]
