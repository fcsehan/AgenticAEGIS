"""End-to-end tests for the Action.user_intent threading (Epic 30).

AEGIS-3001 added the field. AEGIS-3002 asserts that the Guard's verdict
is *neutral* with respect to user_intent — the field is purely audit-side
and visibility-side, never a deontic input. AEGIS-3003 asserts that the
audit record persists user_intent next to the action when it is set.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.audit.trail import AuditTrail
from aegis.guard.action import Action
from aegis.guard.guard import Guard


@pytest.fixture
def small_guard(tmp_path: Path) -> Guard:
    """A v1 guard with one permitted action and one forbidden action."""
    meld = tmp_path / "vocab.meld"
    meld.write_text(
        """
        (aegis-schema-version 1)
        (case TestVocabMt)
        (isa share ActionType)
        (isa leak ActionType)
        (genlPreds permittedToDo-WRT permittedToDo)
        (genlPreds forbiddenToDo-WRT forbiddenToDo)
        (permittedToDo-WRT TestCode agent-1 (share))
        (forbiddenToDo-WRT TestCode agent-1 (leak))
        """,
        encoding="utf-8",
    )
    return Guard.from_meld_files([meld])


class TestVerdictNeutrality:
    """AEGIS-3002: user_intent must never change the verdict."""

    def test_permitted_verdict_independent_of_intent(self, small_guard: Guard) -> None:
        without = small_guard.check(Action(action_type="share", agent_id="agent-1"))
        with_intent = small_guard.check(
            Action(
                action_type="share",
                agent_id="agent-1",
                user_intent="please share with the partners",
            )
        )
        assert without.decision == with_intent.decision
        assert without.reason_type == with_intent.reason_type

    def test_forbidden_verdict_independent_of_intent(self, small_guard: Guard) -> None:
        without = small_guard.check(Action(action_type="leak", agent_id="agent-1"))
        with_intent = small_guard.check(
            Action(
                action_type="leak",
                agent_id="agent-1",
                user_intent="please leak the data",
            )
        )
        assert without.decision == with_intent.decision
        assert without.reason_type == with_intent.reason_type

    def test_intent_variation_never_flips_decision(self, small_guard: Guard) -> None:
        """A spectrum of intent strings must not flip a single verdict."""
        intents = [
            "share something",
            "share absolutely everything",
            "share — but only the public part",
            "I want to leak this",  # adversarial — must still be PERMITTED for action_type=share
            "",  # empty string
        ]
        baseline = small_guard.check(Action(action_type="share", agent_id="agent-1"))
        for intent in intents:
            v = small_guard.check(
                Action(
                    action_type="share",
                    agent_id="agent-1",
                    user_intent=intent,
                )
            )
            assert v.decision == baseline.decision, (
                f"intent {intent!r} flipped the decision"
            )


class TestAuditRecordCarriesIntent:
    """AEGIS-3003: when user_intent is set, the audit record persists it."""

    def test_audit_record_contains_user_intent(self, tmp_path: Path) -> None:
        meld = tmp_path / "vocab.meld"
        meld.write_text(
            """
            (aegis-schema-version 1)
            (case TestVocabMt)
            (isa share ActionType)
            (genlPreds permittedToDo-WRT permittedToDo)
            (permittedToDo-WRT TestCode agent-1 (share))
            """,
            encoding="utf-8",
        )
        audit_path = tmp_path / "audit.jsonl"
        trail = AuditTrail(audit_path)
        guard = Guard.from_meld_files([meld], audit_trail=trail)

        guard.check(
            Action(
                action_type="share",
                agent_id="agent-1",
                user_intent="share the public summary",
            )
        )

        entries = [
            json.loads(line)
            for line in audit_path.read_text().splitlines()
            if line.strip()
        ]
        action_verdicts = [e for e in entries if e["event"] == "ACTION_VERDICT"]
        assert len(action_verdicts) == 1
        assert action_verdicts[0]["action"]["user_intent"] == "share the public summary"

    def test_audit_record_omits_intent_when_unset(self, tmp_path: Path) -> None:
        """Backward-compat: audit records that did not declare an intent
        do not gain a None entry — the key is simply absent."""
        meld = tmp_path / "vocab.meld"
        meld.write_text(
            """
            (aegis-schema-version 1)
            (case TestVocabMt)
            (isa share ActionType)
            (genlPreds permittedToDo-WRT permittedToDo)
            (permittedToDo-WRT TestCode agent-1 (share))
            """,
            encoding="utf-8",
        )
        audit_path = tmp_path / "audit.jsonl"
        trail = AuditTrail(audit_path)
        guard = Guard.from_meld_files([meld], audit_trail=trail)

        guard.check(Action(action_type="share", agent_id="agent-1"))

        entries = [
            json.loads(line)
            for line in audit_path.read_text().splitlines()
            if line.strip()
        ]
        action_verdicts = [e for e in entries if e["event"] == "ACTION_VERDICT"]
        assert len(action_verdicts) == 1
        assert "user_intent" not in action_verdicts[0]["action"]


class TestActionWithIntentRoundtrip:
    """Sanity: Action with user_intent survives the full
    Guard.check pipeline (validation, evaluation, audit) without
    raising, regardless of decision."""

    def test_permitted_path(self, small_guard: Guard) -> None:
        verdict = small_guard.check(
            Action(action_type="share", agent_id="agent-1", user_intent="x")
        )
        assert verdict.decision.value == "PERMITTED"

    def test_forbidden_path(self, small_guard: Guard) -> None:
        verdict = small_guard.check(
            Action(action_type="leak", agent_id="agent-1", user_intent="x")
        )
        assert verdict.decision.value == "FORBIDDEN"

    def test_invalid_action_path(self, small_guard: Guard) -> None:
        """Validation rejection still works when user_intent is set."""
        verdict = small_guard.check(
            Action(
                action_type="share",
                agent_id="agent-1",
                user_intent="x" * 3_000,  # exceeds cap
            )
        )
        # validate_limits surfaces the violation as INVALID_ACTION via
        # the pipeline's stage 1.
        assert verdict.decision.value == "UNDECIDABLE"
        assert "user_intent" in " ".join(verdict.justification_chain).lower()
