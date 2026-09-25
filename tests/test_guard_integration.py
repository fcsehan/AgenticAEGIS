"""Full-stack integration test: .meld files → Guard.check() → Verdict.

Loads the test fixture .meld files and verifies the complete pipeline.
"""

from __future__ import annotations

from pathlib import Path

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "domains"


def _load_guard() -> Guard:
    return Guard.from_meld_files(
        [
            FIXTURE_DIR / "test_ontology.meld",
            FIXTURE_DIR / "test_action_vocab.meld",
            FIXTURE_DIR / "test_deontic_rules.meld",
        ]
    )


class TestGuardIntegration:
    def test_permitted_action(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgent",
                proposition={"dataClassification": "unclassified"},
                context={},
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_forbidden_action(self) -> None:
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgent",
                proposition={"dataClassification": "secret"},
                context={},
            )
        )
        assert verdict.decision == Decision.FORBIDDEN

    def test_unknown_action_type(self) -> None:
        """Action type not in any domain → UNDECIDABLE."""
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="totallyUnknownAction",
                agent_id="intelligenceAgent",
            )
        )
        assert verdict.decision == Decision.UNDECIDABLE

    def test_determinism(self) -> None:
        """Same input → same output, 100 times (I1)."""
        guard = _load_guard()
        action = Action(
            action_type="shareIntelligence",
            agent_id="intelligenceAgent",
            proposition={"dataClassification": "unclassified"},
            context={},
        )
        verdicts = [guard.check(action) for _ in range(100)]
        assert all(v.decision == verdicts[0].decision for v in verdicts)

    def test_verdict_has_justification(self) -> None:
        """Every verdict has a justification chain (I3)."""
        guard = _load_guard()
        verdict = guard.check(
            Action(
                action_type="shareIntelligence",
                agent_id="intelligenceAgent",
            )
        )
        assert verdict.justification_chain  # non-empty

    def test_meld_loads_multiple_mts(self) -> None:
        guard = _load_guard()
        assert guard._kb.fact_count > 0
        assert len(guard._kb.microtheories) >= 3

    def test_norms_extracted(self) -> None:
        guard = _load_guard()
        assert len(guard._norms) >= 5  # 5 deontic rules in test fixture
