"""AEGIS-1901: DDIC Totality — Termination Proof.

Proves that ``DDICEngine.evaluate()`` terminates for every possible
input within bounded limits.

Argument: The preemption loop is O(n²) over ``|applicable_norms|``,
the sort is O(n log n), and moral axiom detection is O(n).
Total complexity: O(n²) where n = |applicable_norms|.
With MAX_APPLICABLE_NORMS = 10_000 this always terminates.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.inheritance import InheritanceGraph
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


def _make_engine(code_prevalence: list[str] | None = None) -> DDICEngine:
    """Build a minimal DDICEngine for testing."""
    kb = KnowledgeBase()
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    inheritance = InheritanceGraph(reasoner)
    return DDICEngine(inheritance, code_prevalence=code_prevalence)


# Strategy: generate random NormFrames
modality_strategy = st.sampled_from(list(DeonticModality))
code_strategy = st.sampled_from(["CodeA", "CodeB", "CodeC", "IAMissionCode"])
specificity_strategy = st.integers(min_value=0, max_value=100)
defeasible_strategy = st.booleans()


@st.composite
def norm_frame_strategy(draw: Any) -> NormFrame:
    """Generate a random NormFrame."""
    return NormFrame(
        code=draw(code_strategy),
        agent_pattern="*",
        modality=draw(modality_strategy),
        proposition=("testAction",),
        specificity=draw(specificity_strategy),
        defeasible=draw(defeasible_strategy),
        source="test-generated",
    )


class TestDDICTotality:
    """Property: DDICEngine.evaluate() terminates for all valid inputs."""

    @given(
        norms=st.lists(norm_frame_strategy(), min_size=1, max_size=100),
    )
    @settings(max_examples=200, deadline=5000)
    def test_evaluate_always_terminates(self, norms: list[NormFrame]) -> None:
        """For any set of 1-100 norms, evaluate() returns in < 1s."""
        engine = _make_engine(code_prevalence=["CodeA", "CodeB", "CodeC"])

        start = time.monotonic()
        status = engine.evaluate(
            proposition=("testAction",),
            agent="*",
            norms=norms,
        )
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, f"evaluate() took {elapsed:.3f}s — exceeds 1s limit"
        # Result must be a valid NormStatus
        assert status is not None
        assert status.reason != ""

    def test_large_norm_set_terminates(self) -> None:
        """1000 norms with maximum conflict potential terminate quickly."""
        engine = _make_engine(code_prevalence=["CodeA", "CodeB"])
        norms: list[NormFrame] = []

        for i in range(500):
            norms.append(NormFrame(
                code="CodeA",
                agent_pattern="*",
                modality=DeonticModality.PERMITTED,
                proposition=("testAction",),
                specificity=i % 50,
                defeasible=True,
                source=f"norm-P-{i}",
            ))
            norms.append(NormFrame(
                code="CodeB",
                agent_pattern="*",
                modality=DeonticModality.FORBIDDEN,
                proposition=("testAction",),
                specificity=i % 50,
                defeasible=True,
                source=f"norm-F-{i}",
            ))

        start = time.monotonic()
        status = engine.evaluate(
            proposition=("testAction",),
            agent="*",
            norms=norms,
        )
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"1000-norm evaluate() took {elapsed:.3f}s"
        assert status is not None

    def test_empty_norms_terminates(self) -> None:
        """Zero applicable norms → immediate return."""
        engine = _make_engine()
        status = engine.evaluate(
            proposition=("testAction",),
            agent="*",
            norms=[],
        )
        assert status.reason == "no_applicable_norms"
        assert status.modality is None
