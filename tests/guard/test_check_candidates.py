"""Tests for ``Guard.check_candidates`` (Epic 32, AEGIS-3203 + AEGIS-3204).

The contract:

- Empty list → UNDECIDABLE / NO_CANDIDATES
- All candidates FORBIDDEN → FORBIDDEN / ALL_CANDIDATES_FORBIDDEN
- At least one PERMITTED → pick narrowest under ``narrowerThan``
- Multiple incomparable minima → deterministic lex tie-break with
  reason ``MULTIPLE_MINIMAL_CANDIDATES``
- ``check_candidates([action]).chosen`` is structurally equivalent to
  ``check(action)`` (backward compatibility "by construction")
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision, ReasonType


@pytest.fixture
def guard_with_subsumption(tmp_path: Path) -> Guard:
    """Build a Guard with a small disambiguation-aware vocabulary plus
    permission rules that distinguish narrowest from broader actions."""
    meld = tmp_path / "narrowest_test.meld"
    meld.write_text(
        """
        (aegis-schema-version 1)
        (case TestVocabMt)

        (isa readDiagnosis ActionType)
        (isa readPatientRecord ActionType)
        (isa readLabResults ActionType)
        (isa shareIntelligence ActionType)

        (actionDescription readDiagnosis "Diagnostic conclusion only.")
        (actionDescription readPatientRecord "Entire patient record.")
        (actionDescription readLabResults "Lab results section.")

        (narrowerThan readDiagnosis readPatientRecord)
        (broaderThan readPatientRecord readDiagnosis)
        (narrowerThan readLabResults readPatientRecord)
        (broaderThan readPatientRecord readLabResults)

        (genlPreds permittedToDo-WRT permittedToDo)
        (genlPreds forbiddenToDo-WRT forbiddenToDo)

        (permittedToDo-WRT TestCode agent-1 (readDiagnosis))
        (permittedToDo-WRT TestCode agent-1 (readPatientRecord))
        (permittedToDo-WRT TestCode agent-1 (readLabResults))
        (forbiddenToDo-WRT TestCode agent-1 (shareIntelligence))
        """,
        encoding="utf-8",
    )
    return Guard.from_meld_files([meld])


class TestEmptyInput:
    def test_returns_undecidable_no_candidates(self, guard_with_subsumption: Guard) -> None:
        result = guard_with_subsumption.check_candidates([])
        assert result.chosen.decision == Decision.UNDECIDABLE
        assert result.chosen.reason_type == ReasonType.NO_CANDIDATES
        assert result.per_candidate == ()
        assert result.minimal_candidates == ()


class TestAllForbidden:
    def test_all_forbidden_consolidates_to_forbidden(self, guard_with_subsumption: Guard) -> None:
        result = guard_with_subsumption.check_candidates(
            [Action(action_type="shareIntelligence", agent_id="agent-1")]
        )
        assert result.chosen.decision == Decision.FORBIDDEN
        assert result.chosen.reason_type == ReasonType.ALL_CANDIDATES_FORBIDDEN
        assert len(result.per_candidate) == 1
        assert result.minimal_candidates == ()


class TestSingleCandidate:
    def test_single_permitted_passes_through(self, guard_with_subsumption: Guard) -> None:
        result = guard_with_subsumption.check_candidates(
            [Action(action_type="readDiagnosis", agent_id="agent-1")]
        )
        assert result.chosen.decision == Decision.PERMITTED
        # Single-element minimum: readDiagnosis is the only candidate.
        assert result.minimal_candidates == ("readDiagnosis",)


class TestNarrowestSelection:
    def test_narrowest_is_chosen_over_broader(self, guard_with_subsumption: Guard) -> None:
        """When both readDiagnosis (narrower) and readPatientRecord
        (broader) are PERMITTED candidates, the narrowest must win."""
        result = guard_with_subsumption.check_candidates([
            Action(action_type="readPatientRecord", agent_id="agent-1"),
            Action(action_type="readDiagnosis", agent_id="agent-1"),
        ])
        assert result.chosen.decision == Decision.PERMITTED
        assert result.minimal_candidates == ("readDiagnosis",)
        assert result.chosen.action_type == "readDiagnosis"

    def test_input_order_does_not_change_choice(self, guard_with_subsumption: Guard) -> None:
        forward = guard_with_subsumption.check_candidates([
            Action(action_type="readDiagnosis", agent_id="agent-1"),
            Action(action_type="readPatientRecord", agent_id="agent-1"),
        ])
        reverse = guard_with_subsumption.check_candidates([
            Action(action_type="readPatientRecord", agent_id="agent-1"),
            Action(action_type="readDiagnosis", agent_id="agent-1"),
        ])
        assert forward.chosen.action_type == reverse.chosen.action_type


class TestMultipleMinima:
    def test_incomparable_minima_use_lex_tiebreak_with_warning(
        self, guard_with_subsumption: Guard,
    ) -> None:
        """readDiagnosis and readLabResults are both narrower than
        readPatientRecord but incomparable to each other. Tie-break by
        lex sort → readDiagnosis < readLabResults lexicographically."""
        result = guard_with_subsumption.check_candidates([
            Action(action_type="readDiagnosis", agent_id="agent-1"),
            Action(action_type="readLabResults", agent_id="agent-1"),
        ])
        assert result.chosen.decision == Decision.PERMITTED
        assert result.chosen.reason_type == ReasonType.MULTIPLE_MINIMAL_CANDIDATES
        assert result.minimal_candidates == ("readDiagnosis", "readLabResults")
        assert result.chosen.action_type == "readDiagnosis"
        # The audit chain documents the tie-break.
        assert any("multiple_minimal" in step for step in result.chosen.justification_chain)


class TestMixedPermittedForbidden:
    def test_only_permitted_candidates_enter_comparison(
        self, guard_with_subsumption: Guard,
    ) -> None:
        result = guard_with_subsumption.check_candidates([
            Action(action_type="shareIntelligence", agent_id="agent-1"),
            Action(action_type="readDiagnosis", agent_id="agent-1"),
            Action(action_type="readPatientRecord", agent_id="agent-1"),
        ])
        assert result.chosen.decision == Decision.PERMITTED
        assert result.chosen.action_type == "readDiagnosis"
        # All three verdicts retained for audit.
        assert len(result.per_candidate) == 3


class TestBackwardCompatibility:
    def test_check_candidates_matches_check_for_single_permitted(
        self, guard_with_subsumption: Guard,
    ) -> None:
        action = Action(action_type="readDiagnosis", agent_id="agent-1")
        v1 = guard_with_subsumption.check(action)
        v2 = guard_with_subsumption.check_candidates([action]).chosen
        # Decision and action_type must match. permit_token_id may differ
        # because each check call mints a fresh token; we ignore that
        # field for backward-compat purposes.
        assert v1.decision == v2.decision
        assert v1.reason_type == v2.reason_type
        assert v1.action_type == v2.action_type
        assert v1.agent_id == v2.agent_id

    def test_check_candidates_matches_check_for_single_forbidden(
        self, guard_with_subsumption: Guard,
    ) -> None:
        action = Action(action_type="shareIntelligence", agent_id="agent-1")
        v1 = guard_with_subsumption.check(action)
        v2 = guard_with_subsumption.check_candidates([action]).chosen
        assert v1.decision == v2.decision == Decision.FORBIDDEN
        # check_candidates re-classifies as ALL_CANDIDATES_FORBIDDEN; the
        # underlying decision remains FORBIDDEN.
        assert v2.reason_type == ReasonType.ALL_CANDIDATES_FORBIDDEN


class TestUserIntentParameter:
    def test_user_intent_is_accepted_but_does_not_affect_decision(
        self, guard_with_subsumption: Guard,
    ) -> None:
        """user_intent is reserved for Epic 30 audit threading; today it
        must not change the decision so we lock that contract in."""
        action = Action(action_type="readDiagnosis", agent_id="agent-1")
        without = guard_with_subsumption.check_candidates([action])
        with_intent = guard_with_subsumption.check_candidates(
            [action], user_intent="show me the diagnosis"
        )
        assert without.chosen.decision == with_intent.chosen.decision
        assert without.chosen.action_type == with_intent.chosen.action_type


class TestAuditLogging:
    """AEGIS-3205: every check_candidates call writes a CANDIDATE_EVALUATION
    audit record with the per-candidate verdicts, the antichain of
    minimal candidates, and the chosen action."""

    def test_audit_record_contains_all_candidates(self, tmp_path: Path) -> None:
        from aegis.audit.trail import AuditTrail

        meld = tmp_path / "vocab.meld"
        meld.write_text(
            """
            (aegis-schema-version 1)
            (case TestVocabMt)
            (isa A ActionType)
            (isa B ActionType)
            (narrowerThan A B)
            (broaderThan B A)
            (genlPreds permittedToDo-WRT permittedToDo)
            (permittedToDo-WRT TestCode agent-1 (A))
            (permittedToDo-WRT TestCode agent-1 (B))
            """,
            encoding="utf-8",
        )
        audit_path = tmp_path / "audit.jsonl"
        trail = AuditTrail(audit_path)

        guard = Guard.from_meld_files([meld], audit_trail=trail)
        guard.check_candidates([
            Action(action_type="A", agent_id="agent-1"),
            Action(action_type="B", agent_id="agent-1"),
        ], user_intent="pick the right one")

        # Read back the audit log and find the CANDIDATE_EVALUATION entry.
        import json
        entries = [
            json.loads(line)
            for line in audit_path.read_text().splitlines()
            if line.strip()
        ]
        candidate_entries = [e for e in entries if e["event"] == "CANDIDATE_EVALUATION"]
        assert len(candidate_entries) == 1, "expected exactly one CANDIDATE_EVALUATION"

        record = candidate_entries[0]
        details = record["action"]
        assert isinstance(details, dict)
        assert {c["action"]["action_type"] for c in details["candidates"]} == {"A", "B"}
        assert details["minimal_candidates"] == ["A"]
        assert details["chosen_action_type"] == "A"
        assert details["chosen_decision"] == "PERMITTED"
        assert details["user_intent"] == "pick the right one"

    def test_audit_record_for_empty_input(self, tmp_path: Path) -> None:
        from aegis.audit.trail import AuditTrail

        meld = tmp_path / "vocab.meld"
        meld.write_text(
            """
            (aegis-schema-version 1)
            (case TestVocabMt)
            (isa A ActionType)
            """,
            encoding="utf-8",
        )
        audit_path = tmp_path / "audit.jsonl"
        trail = AuditTrail(audit_path)

        guard = Guard.from_meld_files([meld], audit_trail=trail)
        result = guard.check_candidates([])
        assert result.chosen.reason_type == ReasonType.NO_CANDIDATES

        import json
        entries = [
            json.loads(line)
            for line in audit_path.read_text().splitlines()
            if line.strip()
        ]
        candidate_entries = [e for e in entries if e["event"] == "CANDIDATE_EVALUATION"]
        assert len(candidate_entries) == 1
        assert candidate_entries[0]["action"]["candidates"] == []
