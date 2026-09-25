"""Tests for AEGIS-2704 — MELD v1 plan-constraint predicate
registration."""

from __future__ import annotations

import logging

import pytest

from aegis.deontic.plan_norm_frame import PlanNormFrame
from aegis.errors import MeldSyntaxError
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import (
    PLAN_CONSTRAINT_PREDICATES,
    MeldLoader,
    extract_plan_constraint,
)


def _load(text: str) -> MeldLoader:
    """Helper: load *text* into a fresh MeldLoader and return it."""
    kb = KnowledgeBase()
    loader = MeldLoader(kb)
    loader.load_string(text, file="test.meld")
    return loader


# ── 1. Predicate-set registration ──────────────────────────────────


class TestPredicateRegistration:
    def test_four_predicates_registered(self) -> None:
        assert {
            "obligateSequence",
            "forbidAggregate",
            "obligateWithin",
            "requirePrecondition",
        } == PLAN_CONSTRAINT_PREDICATES

    def test_loader_exposes_plan_constraints_property(self) -> None:
        loader = _load("(case TestMt)")
        assert loader.plan_constraints == []

    def test_property_returns_independent_copy(self) -> None:
        """plan_constraints returns a fresh list each call so mutations
        don't leak into the loader's internal state."""
        loader = _load("(case TestMt)")
        external = loader.plan_constraints
        external.append(PlanNormFrame(predicate="x", args=()))
        assert loader.plan_constraints == []


# ── 2. Happy-path extraction per predicate ─────────────────────────


class TestObligateSequence:
    def test_basic_form_extracted(self) -> None:
        loader = _load(
            """
            (case TestMt)
            (obligateSequence runTests deploy)
            """
        )
        assert len(loader.plan_constraints) == 1
        frame = loader.plan_constraints[0]
        assert frame.predicate == "obligateSequence"
        assert frame.args == ("runTests", "deploy")
        assert frame.agent_pattern == "*"
        assert frame.source.startswith("test.meld:")

    def test_wrong_arity_fails_loud(self) -> None:
        with pytest.raises(MeldSyntaxError, match="expects 2 arguments"):
            _load(
                """
                (case TestMt)
                (obligateSequence runTests)
                """
            )

    def test_three_args_fails(self) -> None:
        with pytest.raises(MeldSyntaxError, match="expects 2"):
            _load(
                """
                (case TestMt)
                (obligateSequence a b c)
                """
            )


class TestForbidAggregate:
    def test_basic_form_extracted(self) -> None:
        loader = _load(
            """
            (case TestMt)
            (forbidAggregate deploy 3)
            """
        )
        frame = loader.plan_constraints[0]
        assert frame.predicate == "forbidAggregate"
        assert frame.args == ("deploy", 3)

    def test_zero_count_allowed(self) -> None:
        """forbidAggregate ?a 0 means the action may not appear at all
        — semantically meaningful, not an error."""
        loader = _load(
            """
            (case TestMt)
            (forbidAggregate deploy 0)
            """
        )
        assert loader.plan_constraints[0].args == ("deploy", 0)

    def test_non_int_max_count_fails(self) -> None:
        with pytest.raises(MeldSyntaxError, match="must be an integer"):
            _load(
                """
                (case TestMt)
                (forbidAggregate deploy threeTimes)
                """
            )

    def test_negative_max_count_fails(self) -> None:
        with pytest.raises(MeldSyntaxError, match=">= 0"):
            _load(
                """
                (case TestMt)
                (forbidAggregate deploy -1)
                """
            )


class TestObligateWithin:
    def test_immediate_symbol_accepted(self) -> None:
        loader = _load(
            """
            (case TestMt)
            (obligateWithin alert immediate)
            """
        )
        frame = loader.plan_constraints[0]
        assert frame.args == ("alert", "immediate")

    def test_same_session_symbol_accepted(self) -> None:
        loader = _load(
            """
            (case TestMt)
            (obligateWithin notify same-session)
            """
        )
        assert loader.plan_constraints[0].args[1] == "same-session"

    def test_end_of_plan_symbol_accepted(self) -> None:
        loader = _load(
            """
            (case TestMt)
            (obligateWithin cleanup end-of-plan)
            """
        )
        assert loader.plan_constraints[0].args[1] == "end-of-plan"

    def test_integer_seconds_accepted(self) -> None:
        loader = _load(
            """
            (case TestMt)
            (obligateWithin deploy 300)
            """
        )
        assert loader.plan_constraints[0].args == ("deploy", 300)

    def test_zero_seconds_accepted(self) -> None:
        loader = _load(
            """
            (case TestMt)
            (obligateWithin deploy 0)
            """
        )
        assert loader.plan_constraints[0].args[1] == 0

    def test_unknown_symbol_rejected(self) -> None:
        with pytest.raises(MeldSyntaxError, match="must be one of"):
            _load(
                """
                (case TestMt)
                (obligateWithin deploy nextTuesday)
                """
            )

    def test_negative_seconds_rejected(self) -> None:
        with pytest.raises(MeldSyntaxError, match=">= 0"):
            _load(
                """
                (case TestMt)
                (obligateWithin deploy -5)
                """
            )


class TestRequirePrecondition:
    def test_predicate_form_extracted(self) -> None:
        loader = _load(
            """
            (case TestMt)
            (requirePrecondition deploy (testStatus passed))
            """
        )
        frame = loader.plan_constraints[0]
        assert frame.predicate == "requirePrecondition"
        assert frame.args[0] == "deploy"
        # Inner predicate parsed as a tuple.
        assert frame.args[1] == ("testStatus", "passed")


# ── 3. Co-existence & isolation ────────────────────────────────────


class TestCoexistenceWithExistingMeld:
    def test_plan_constraint_does_not_become_norm(self) -> None:
        """Plan-constraint predicates must not leak into the NormFrame
        list — they live on a parallel pipeline."""
        loader = _load(
            """
            (case TestMt)
            (forbidAggregate deploy 3)
            """
        )
        assert loader.norms == []
        assert len(loader.plan_constraints) == 1

    def test_existing_v1_files_load_unchanged(self) -> None:
        """A v1 file with norms but no plan-constraints loads normally
        and exposes an empty plan_constraints list."""
        loader = _load(
            """
            (case TestMt)
            (oughtToDo Alice helpStranger)
            """
        )
        assert len(loader.norms) == 1
        assert loader.plan_constraints == []

    def test_norms_and_plan_constraints_in_same_file(self) -> None:
        loader = _load(
            """
            (case TestMt)
            (oughtToDo Alice helpStranger)
            (obligateSequence runTests deploy)
            """
        )
        assert len(loader.norms) == 1
        assert len(loader.plan_constraints) == 1

    def test_plan_constraint_predicates_do_not_warn(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Registering them in _KNOWN_PREDICATES prevents the
        unknown-predicate warning from firing."""
        with caplog.at_level(logging.WARNING, logger="aegis.kb.meld_loader"):
            _load(
                """
                (case TestMt)
                (forbidAggregate deploy 3)
                """
            )
        assert not any(
            "Unknown predicate" in rec.message for rec in caplog.records
        )


# ── 4. extract_plan_constraint as a standalone function ───────────


class TestExtractPlanConstraintFunction:
    def test_returns_none_for_non_plan_predicate(self) -> None:
        assertion = ("oughtToDo", "Alice", "helpStranger")
        assert extract_plan_constraint(assertion, "TestMt", "x:1") is None

    def test_returns_none_for_empty_assertion(self) -> None:
        assert extract_plan_constraint((), "TestMt", "x:1") is None

    def test_source_propagated(self) -> None:
        assertion = ("forbidAggregate", "deploy", 3)
        frame = extract_plan_constraint(assertion, "TestMt", "myfile.meld:42")
        assert frame is not None
        assert frame.source == "myfile.meld:42"
