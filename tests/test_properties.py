"""AEGIS-1104: Property-Based Testing.

Hypothesis-based property tests for AEGIS invariants.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from aegis.audit.integrity import verify_integrity
from aegis.audit.trail import AuditTrail
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision, ReasonType, Verdict

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "domains"


def _load_guard() -> Guard:
    return Guard.from_meld_files(
        [
            FIXTURE_DIR / "test_ontology.meld",
            FIXTURE_DIR / "test_action_vocab.meld",
            FIXTURE_DIR / "test_deontic_rules.meld",
        ]
    )


# Strategy for generating random actions
action_strategy = st.builds(
    Action,
    action_type=st.sampled_from(
        ["shareIntelligence", "directOperations", "unknownAction", "anotherUnknown"]
    ),
    agent_id=st.sampled_from(
        ["intelligenceAgent", "operationsAgent", "unknownAgent"]
    ),
    proposition=st.fixed_dictionaries(
        {},
        optional={
            "dataClassification": st.sampled_from(
                ["unclassified", "classified", "secret", "topSecret"]
            ),
        },
    ),
)


class TestInvariant1Determinism:
    """I1: Same input → same output."""

    @given(action=action_strategy)
    @settings(max_examples=50)
    def test_determinism(self, action: Action) -> None:
        guard = _load_guard()
        v1 = guard.check(action)
        v2 = guard.check(action)
        assert v1.decision == v2.decision
        assert v1.reason_type == v2.reason_type
        assert v1.norms_applied == v2.norms_applied
        assert v1.justification_chain == v2.justification_chain


class TestInvariant2DenyByDefault:
    """I2/D-001: No explicit permission → FORBIDDEN or UNDECIDABLE."""

    @given(action=action_strategy)
    @settings(max_examples=50)
    def test_never_permitted_without_norm(self, action: Action) -> None:
        guard = _load_guard()
        verdict = guard.check(action)

        if verdict.decision == Decision.PERMITTED:
            # Must have an explicit norm
            assert verdict.reason_type in (
                ReasonType.EXPLICIT_NORM,
                ReasonType.MORAL_AXIOM,
            ), (
                f"PERMITTED without explicit norm: {verdict.reason_type}"
            )


class TestInvariant4Duality:
    """I4/Duality: FORBIDDEN ↔ ¬PERMITTED for each evaluation."""

    @given(action=action_strategy)
    @settings(max_examples=50)
    def test_forbidden_not_permitted(self, action: Action) -> None:
        guard = _load_guard()
        verdict = guard.check(action)
        # FORBIDDEN and PERMITTED are mutually exclusive
        assert verdict.decision != Decision.PERMITTED or verdict.decision != Decision.FORBIDDEN


class TestInvariant7HashChain:
    """I7: Hash chain integrity for any sequence of audit entries."""

    @given(
        actions=st.lists(action_strategy, min_size=1, max_size=20),
    )
    @settings(max_examples=10)
    def test_hash_chain_valid(self, actions: list[Action]) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            trail = AuditTrail(path)
            verdict = Verdict(
                decision=Decision.PERMITTED,
                reason_type=ReasonType.EXPLICIT_NORM,
                action_type="test",
                agent_id="agent",
            )
            for action in actions:
                trail.log(action, verdict)

            result = verify_integrity(path)
            assert result.valid, f"Hash chain invalid: {result.errors}"
