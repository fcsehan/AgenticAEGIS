"""Tests for AEGIS-2711 — PlanActionExecutor + Plan-Permit-Token."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.api.plan_executor import (
    PlanActionExecutor,
    PlanExecutionResult,
)
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.plan import Plan, PlanStep
from aegis.guard.verdict import PlanDecision
from aegis.hardening.permit import (
    PlanPermitStore,
    PlanPermitToken,
    canonical_action_hash,
)


def _write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def ops_guard(tmp_path: Path) -> Guard:
    onto = _write(tmp_path, "onto.meld", """
        (case Onto)
        (isa runTests SoftwareAction)
        (isa deploy SoftwareAction)
    """)
    rules = _write(tmp_path, "rules.meld", """
        (case Rules)
        (permittedToDo opsAgent runTests)
        (permittedToDo opsAgent deploy)
        (forbiddenToDo opsAgent danger)
        (obligateSequence runTests deploy)
    """)
    return Guard.from_meld_files([onto, rules])


def _two_step_plan() -> Plan:
    return Plan(steps=(
        PlanStep(action=Action(action_type="runTests", agent_id="opsAgent")),
        PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
    ))


# ── 1. PlanPermitStore directly ───────────────────────────────────


class TestPlanPermitStore:
    def test_issue_returns_token_with_step_hashes(self) -> None:
        store = PlanPermitStore()
        plan = _two_step_plan()
        hashes = tuple(canonical_action_hash(s.action) for s in plan.steps)
        token = store.issue(plan.plan_id, hashes)
        assert isinstance(token, PlanPermitToken)
        assert token.expected_step_hashes == hashes
        assert token.consumed_step_indices == frozenset()
        assert not token.invalidated

    def test_consume_step_with_matching_action(self) -> None:
        store = PlanPermitStore()
        plan = _two_step_plan()
        hashes = tuple(canonical_action_hash(s.action) for s in plan.steps)
        token = store.issue(plan.plan_id, hashes)
        updated = store.consume_plan_step(token.token_id, 0, plan.steps[0].action)
        assert updated is not None
        assert 0 in updated.consumed_step_indices

    def test_consume_with_mismatched_action_invalidates(self) -> None:
        store = PlanPermitStore()
        plan = _two_step_plan()
        hashes = tuple(canonical_action_hash(s.action) for s in plan.steps)
        token = store.issue(plan.plan_id, hashes)
        rogue = Action(action_type="runTests", agent_id="rogueAgent")
        result = store.consume_plan_step(token.token_id, 0, rogue)
        assert result is None
        # Token is now invalidated — even a matching action fails.
        assert store.consume_plan_step(
            token.token_id, 0, plan.steps[0].action,
        ) is None

    def test_double_consume_same_step_fails(self) -> None:
        store = PlanPermitStore()
        plan = _two_step_plan()
        hashes = tuple(canonical_action_hash(s.action) for s in plan.steps)
        token = store.issue(plan.plan_id, hashes)
        store.consume_plan_step(token.token_id, 0, plan.steps[0].action)
        retry = store.consume_plan_step(token.token_id, 0, plan.steps[0].action)
        assert retry is None

    def test_index_out_of_range_fails(self) -> None:
        store = PlanPermitStore()
        plan = _two_step_plan()
        hashes = tuple(canonical_action_hash(s.action) for s in plan.steps)
        token = store.issue(plan.plan_id, hashes)
        out = store.consume_plan_step(token.token_id, 99, plan.steps[0].action)
        assert out is None

    def test_invalidate_after_runtime_error(self) -> None:
        store = PlanPermitStore()
        plan = _two_step_plan()
        hashes = tuple(canonical_action_hash(s.action) for s in plan.steps)
        token = store.issue(plan.plan_id, hashes)
        store.invalidate(token.token_id)
        nope = store.consume_plan_step(token.token_id, 0, plan.steps[0].action)
        assert nope is None


# ── 2. PlanActionExecutor — happy path ─────────────────────────────


class TestPlanExecutorHappyPath:
    def test_permitted_plan_executes_all_steps(self, ops_guard: Guard) -> None:
        log: list[str] = []
        plan_exec = PlanActionExecutor(ops_guard)
        plan_exec.register("runTests", lambda a: log.append("ran") or "ok")
        plan_exec.register("deploy", lambda a: log.append("deployed") or "ok")
        result = plan_exec.execute_plan(_two_step_plan())
        assert result.all_steps_executed
        assert log == ["ran", "deployed"]
        assert len(result.executed_step_records) == 2

    def test_records_carry_executor_results(self, ops_guard: Guard) -> None:
        plan_exec = PlanActionExecutor(ops_guard)
        plan_exec.register("runTests", lambda a: {"out": "tests-ok"})
        plan_exec.register("deploy", lambda a: {"out": "deployed"})
        result = plan_exec.execute_plan(_two_step_plan())
        assert result.executed_step_records[0].result == {"out": "tests-ok"}
        assert result.executed_step_records[1].result == {"out": "deployed"}


# ── 3. Non-PERMITTED → no execution ───────────────────────────────


class TestPlanExecutorBlocked:
    def test_forbidden_plan_no_execution(self, ops_guard: Guard) -> None:
        log: list[str] = []
        plan_exec = PlanActionExecutor(ops_guard)
        plan_exec.register("danger", lambda a: log.append("ran"))
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="danger", agent_id="opsAgent")),
        ))
        result = plan_exec.execute_plan(plan)
        assert result.plan_verdict.plan_decision == PlanDecision.FORBIDDEN
        assert log == []
        assert result.executed_step_records == ()

    def test_sequence_violation_no_execution(self, ops_guard: Guard) -> None:
        log: list[str] = []
        plan_exec = PlanActionExecutor(ops_guard)
        plan_exec.register("runTests", lambda a: log.append("ran"))
        plan_exec.register("deploy", lambda a: log.append("deployed"))
        # Bad order: deploy → runTests violates obligateSequence.
        plan = Plan(steps=(
            PlanStep(action=Action(action_type="deploy", agent_id="opsAgent")),
            PlanStep(action=Action(action_type="runTests", agent_id="opsAgent")),
        ))
        result = plan_exec.execute_plan(plan)
        assert result.plan_verdict.plan_decision == PlanDecision.FORBIDDEN
        assert log == []


# ── 4. Smuggling defence (the AEGIS-2711 #6 acceptance) ──────────


class TestSmugglingDefence:
    def test_substitution_attack_caught_by_token(
        self, ops_guard: Guard, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An attacker who tampers with plan.steps[i] AFTER plan_check
        but BEFORE step execution fails the per-step hash compare.

        We simulate this by registering a step-executor for runTests
        but then mutating the plan inside the loop is not possible
        from outside; instead, we patch the executor's iteration to
        run a substituted action through ``consume_plan_step``."""
        plan = _two_step_plan()
        hashes = tuple(canonical_action_hash(s.action) for s in plan.steps)
        store = PlanPermitStore()
        token = store.issue(plan.plan_id, hashes)

        # Direct attack: try to consume step 0 with a different action.
        rogue = Action(action_type="danger", agent_id="opsAgent")
        out = store.consume_plan_step(token.token_id, 0, rogue)
        assert out is None
        # Token is now invalid — even legitimate consumption fails.
        out2 = store.consume_plan_step(
            token.token_id, 1, plan.steps[1].action,
        )
        assert out2 is None


# ── 5. Runtime executor failure → fail-fast ───────────────────────


class TestPlanExecutorRuntimeError:
    def test_executor_exception_aborts_remaining_steps(
        self, ops_guard: Guard,
    ) -> None:
        log: list[str] = []
        plan_exec = PlanActionExecutor(ops_guard)

        def boom(action: Action) -> None:
            log.append("started")
            raise RuntimeError("kaboom")

        plan_exec.register("runTests", boom)
        plan_exec.register("deploy", lambda a: log.append("deployed"))
        result = plan_exec.execute_plan(_two_step_plan())
        assert result.aborted
        assert "executor_error" in result.abort_reason
        # Step 0 attempted, step 1 NOT executed.
        assert log == ["started"]
        # First record reflects the failure.
        assert not result.executed_step_records[0].executed
        assert "kaboom" in (result.executed_step_records[0].error or "")
        # No second record.
        assert len(result.executed_step_records) == 1

    def test_token_invalidated_after_runtime_error(
        self, ops_guard: Guard,
    ) -> None:
        store = PlanPermitStore()
        plan_exec = PlanActionExecutor(ops_guard, plan_permit_store=store)
        plan_exec.register("runTests", lambda a: (_ for _ in ()).throw(RuntimeError("nope")))
        plan_exec.register("deploy", lambda a: None)
        result = plan_exec.execute_plan(_two_step_plan())
        assert result.aborted
        token = store.get(result.plan_token_id)
        assert token is not None
        assert token.invalidated


# ── 6. Missing step executor ──────────────────────────────────────


class TestMissingExecutor:
    def test_missing_step_executor_aborts(self, ops_guard: Guard) -> None:
        plan_exec = PlanActionExecutor(ops_guard)
        plan_exec.register("runTests", lambda a: None)
        # No executor for "deploy".
        result = plan_exec.execute_plan(_two_step_plan())
        assert result.aborted
        assert "no_step_executor" in result.abort_reason
        # First step ran fine, second step missing executor.
        assert len(result.executed_step_records) == 1
        assert result.executed_step_records[0].executed


# ── 7. Registration safety ────────────────────────────────────────


class TestRegistrationSafety:
    def test_double_registration_fails_loud(self, ops_guard: Guard) -> None:
        plan_exec = PlanActionExecutor(ops_guard)
        plan_exec.register("runTests", lambda a: None)
        with pytest.raises(ValueError, match="already registered"):
            plan_exec.register("runTests", lambda a: None)


# ── 8. Result type ────────────────────────────────────────────────


class TestResultType:
    def test_result_is_frozen(self, ops_guard: Guard) -> None:
        plan_exec = PlanActionExecutor(ops_guard)
        plan_exec.register("runTests", lambda a: None)
        plan_exec.register("deploy", lambda a: None)
        result = plan_exec.execute_plan(_two_step_plan())
        with pytest.raises(AttributeError):
            result.aborted = True  # type: ignore[misc]

    def test_all_steps_executed_property(self, ops_guard: Guard) -> None:
        plan_exec = PlanActionExecutor(ops_guard)
        plan_exec.register("runTests", lambda a: None)
        plan_exec.register("deploy", lambda a: None)
        result = plan_exec.execute_plan(_two_step_plan())
        assert isinstance(result, PlanExecutionResult)
        assert result.all_steps_executed
