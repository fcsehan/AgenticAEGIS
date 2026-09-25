"""AEGIS-2714 (Epic 27) — Pl-Aeq theorem.

  Pl-Aeq:  ∀ action a.  Plan.from_action(a).per_step_verdicts[0].decision
                       == Guard.check(a).decision

This is the backward-compatibility-by-construction property. The
single-step-plan call must be operationally indistinguishable from
the action-API call. Tested across the full DevOps domain plus a
synthetic permissive/forbidding domain to catch any regressions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.plan import Plan
from aegis.guard.verdict import Decision

DEVOPS = Path("aegis/domains/devops")


@pytest.fixture(scope="module")
def devops_guard() -> Guard:
    return Guard.from_meld_files([
        DEVOPS / "DevOpsDomainOntologyMt.meld",
        DEVOPS / "DevOpsActionVocabMt.meld",
        DEVOPS / "DevOpsDeonticRulesMt.meld",
        DEVOPS / "DevOpsPlanNormsMt.meld",
    ])


@pytest.fixture(scope="module")
def synthetic_guard(tmp_path_factory: pytest.TempPathFactory) -> Guard:
    """Tiny synthetic domain for ergonomic equivalence smoke-tests."""
    d = tmp_path_factory.mktemp("synth")
    onto = d / "onto.meld"
    onto.write_text("""
        (case Onto)
        (isa doX SoftwareAction)
        (isa doY SoftwareAction)
        (isa doZ SoftwareAction)
    """)
    rules = d / "rules.meld"
    rules.write_text("""
        (case Rules)
        (permittedToDo agent-A doX)
        (permittedToDo agent-A doY)
        (forbiddenToDo agent-A doZ)
    """)
    return Guard.from_meld_files([onto, rules])


def _equivalent(guard: Guard, action: Action) -> bool:
    a_decision = guard.check(action).decision
    p_decision = guard.plan_check(
        Plan.from_action(action)
    ).per_step_verdicts[0].decision
    return a_decision == p_decision


# ── Synthetic domain — every modality ────────────────────────────


class TestSyntheticEquivalence:
    def test_permitted_action(self, synthetic_guard: Guard) -> None:
        assert _equivalent(
            synthetic_guard,
            Action(action_type="doX", agent_id="agent-A"),
        )

    def test_forbidden_action(self, synthetic_guard: Guard) -> None:
        assert _equivalent(
            synthetic_guard,
            Action(action_type="doZ", agent_id="agent-A"),
        )

    def test_unknown_action_type(self, synthetic_guard: Guard) -> None:
        assert _equivalent(
            synthetic_guard,
            Action(action_type="phantomOp", agent_id="agent-A"),
        )

    def test_unknown_agent(self, synthetic_guard: Guard) -> None:
        assert _equivalent(
            synthetic_guard,
            Action(action_type="doX", agent_id="agent-Z"),
        )

    def test_action_with_proposition_data(self, synthetic_guard: Guard) -> None:
        assert _equivalent(
            synthetic_guard,
            Action(
                action_type="doX",
                agent_id="agent-A",
                proposition={"path": "/tmp/foo"},
            ),
        )

    def test_action_with_user_intent(self, synthetic_guard: Guard) -> None:
        assert _equivalent(
            synthetic_guard,
            Action(
                action_type="doY",
                agent_id="agent-A",
                user_intent="please do Y",
            ),
        )


# ── DevOps domain — wider coverage ───────────────────────────────


class TestDevOpsEquivalence:
    @pytest.mark.parametrize("action_type", [
        "readFile", "modifyFile", "buildArtifact", "testArtifact",
        "deployArtifact", "emergencyRollback", "requestApproval",
        "executeRemoteCode", "forceModifyRepository",
        "modifySensitiveConfig", "phantomOp",
    ])
    def test_action_equivalence(
        self, devops_guard: Guard, action_type: str,
    ) -> None:
        for agent in ("ciAgent", "opencodeAgent", "developerAgent"):
            action = Action(action_type=action_type, agent_id=agent)
            assert _equivalent(devops_guard, action), (
                f"Aequivalenz violated for action_type={action_type}, "
                f"agent={agent}"
            )


# ── Edge cases ───────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_proposition(self, synthetic_guard: Guard) -> None:
        assert _equivalent(
            synthetic_guard,
            Action(action_type="doX", agent_id="agent-A", proposition={}),
        )

    def test_decision_is_one_of_three(self, synthetic_guard: Guard) -> None:
        """Sanity: per-step Verdict.decision must be a Decision enum."""
        action = Action(action_type="doX", agent_id="agent-A")
        plan_verdict = synthetic_guard.plan_check(Plan.from_action(action))
        assert plan_verdict.per_step_verdicts[0].decision in {
            Decision.PERMITTED, Decision.FORBIDDEN, Decision.UNDECIDABLE,
        }
