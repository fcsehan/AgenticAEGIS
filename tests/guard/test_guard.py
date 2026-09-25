"""Tests for Guard (top-level)."""

from __future__ import annotations

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.inheritance import InheritanceGraph
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.registry import ActionTypeRegistry
from aegis.guard.verdict import Decision, ReasonType
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


def _make_guard() -> Guard:
    kb = KnowledgeBase()
    kb.create_mt("test")
    kb.assert_fact(("isa", "share", "MissionActionType"), "test")
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    graph = InheritanceGraph(reasoner)
    ddic = DDICEngine(graph)
    registry = ActionTypeRegistry.from_kb(kb)
    norms = [
        NormFrame(
            code="TestCode",
            agent_pattern="agent-007",
            modality=DeonticModality.PERMITTED,
            proposition=("share",),
            source="test:1",
        ),
        NormFrame(
            code="TestCode",
            agent_pattern="agent-evil",
            modality=DeonticModality.FORBIDDEN,
            proposition=("share",),
            source="test:2",
        ),
    ]
    return Guard(kb=kb, norms=norms, registry=registry, ddic=ddic)


class TestGuard:
    def test_permitted(self) -> None:
        guard = _make_guard()
        verdict = guard.check(
            Action(
                action_type="share",
                agent_id="agent-007",
            )
        )
        assert verdict.decision == Decision.PERMITTED

    def test_never_crashes(self) -> None:
        """Guard.check() never raises — D-004."""
        guard = _make_guard()
        # Even with weird input, should return a verdict
        verdict = guard.check(
            Action(
                action_type="",
                agent_id="",
            )
        )
        assert isinstance(verdict.decision, Decision)

    def test_exception_returns_undecidable(self) -> None:
        """Internal errors → UNDECIDABLE, never PERMITTED."""
        guard = _make_guard()
        # Force an error by using a broken DDICEngine
        guard._ddic = None  # type: ignore[assignment]
        verdict = guard.check(
            Action(
                action_type="share",
                agent_id="agent-007",
            )
        )
        assert verdict.decision == Decision.UNDECIDABLE
        assert verdict.reason_type == ReasonType.INTERNAL_ERROR

    def test_v1_legacy_path_marks_evaluation_mode_v1_legacy(self) -> None:
        """AEGIS-2309 #4: Guards built with the direct constructor (no
        compiled DDICModule) carry ``evaluation_mode='v1_legacy'`` so an
        auditor can distinguish that path from a compiled v1 module."""
        guard = _make_guard()
        verdict = guard.check(
            Action(action_type="share", agent_id="agent-007")
        )
        assert verdict.evaluation_mode == "v1_legacy"

    def test_internal_error_verdict_still_carries_evaluation_mode(self) -> None:
        """Even on the error path the evaluation_mode must be present so
        audit logs do not lose the strategy attribution."""
        guard = _make_guard()
        guard._ddic = None  # type: ignore[assignment]
        verdict = guard.check(
            Action(action_type="share", agent_id="agent-007")
        )
        assert verdict.evaluation_mode == "v1_legacy"

    def test_v1_compiled_path_marks_evaluation_mode_legacy(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """AEGIS-2309 #4: v1 .meld files loaded through ``from_meld_files``
        are compiled into a DDICModule with ``resolution_strategy='legacy'``.
        Verdicts from this path must surface ``evaluation_mode='legacy'`` —
        distinct from the direct-constructor ``v1_legacy`` path."""
        from pathlib import Path

        ontology = Path(tmp_path) / "OntologyMt.meld"
        ontology.write_text(
            """
            (aegis-schema-version 1)
            (case TestOntologyMt)
            (isa share ActionType)
            (genlPreds permittedToDo-WRT permittedToDo)
            """,
            encoding="utf-8",
        )
        rules = Path(tmp_path) / "RulesMt.meld"
        rules.write_text(
            """
            (aegis-schema-version 1)
            (case TestRulesMt)
            (permittedToDo-WRT TestCode agent-007 (share))
            """,
            encoding="utf-8",
        )

        guard = Guard.from_meld_files([ontology, rules])
        verdict = guard.check(
            Action(action_type="share", agent_id="agent-007")
        )
        assert verdict.evaluation_mode == "legacy"
