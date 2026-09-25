"""AEGIS-1906: Extended Determinism (strengthened I1).

Extends the basic 100x determinism test to:
1. All action types from loaded domains
2. Concurrent access (multi-threaded)
3. Norm shuffle stability (sort-order independence)
4. Timing variance bounds
"""

from __future__ import annotations

import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from aegis.deontic.modality import DeonticModality
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.inheritance import InheritanceGraph
from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase


def _load_guard() -> Guard:
    """Load Guard from available domain files."""
    domain_dir = Path(__file__).resolve().parents[2] / "aegis" / "domains"
    for name in ["iamission", "ifc"]:
        d = domain_dir / name
        if not d.exists():
            continue
        meld_files = sorted(d.glob("*.meld"))
        if meld_files:
            return Guard.from_meld_files(
                meld_files,
                code_prevalence=["IAMissionCode"],
            )
    ref_dir = Path(__file__).resolve().parents[2] / "Referenz" / "opencyc-flatfiles"
    meld_files = sorted(ref_dir.glob("IAMission*.meld"))
    if meld_files:
        return Guard.from_meld_files(meld_files, code_prevalence=["IAMissionCode"])
    pytest.skip("No domain MELD files available")
    raise AssertionError("unreachable")


def _make_engine() -> DDICEngine:
    kb = KnowledgeBase()
    kb.freeze()
    reasoner = BuiltinEngine(kb)
    reasoner.compute()
    inheritance = InheritanceGraph(reasoner)
    return DDICEngine(inheritance, code_prevalence=["CodeA", "CodeB"])


class TestDeterminismExtended:
    """Extended determinism: same input → same output, always."""

    def test_100x_all_action_types(self) -> None:
        """Every registered action type produces identical verdicts across 100 runs."""
        guard = _load_guard()
        for action_type in guard._registry.action_types:
            action = Action(
                action_type=action_type,
                agent_id="test-agent",
                proposition={},
            )
            first_verdict = guard.check(action)
            for _ in range(99):
                verdict = guard.check(action)
                assert verdict.decision == first_verdict.decision, (
                    f"Non-deterministic: {action_type} gave different decisions"
                )
                assert verdict.reason_type == first_verdict.reason_type

    def test_concurrent_access_10_threads(self) -> None:
        """10 threads checking the same action 100x each → all identical."""
        guard = _load_guard()
        action_types = guard._registry.action_types
        if not action_types:
            pytest.skip("No action types registered")

        action = Action(
            action_type=action_types[0],
            agent_id="test-agent",
            proposition={},
        )
        expected = guard.check(action)

        def check_100x() -> list[str]:
            results: list[str] = []
            for _ in range(100):
                v = guard.check(action)
                results.append(v.decision.value)
            return results

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_100x) for _ in range(10)]
            for future in as_completed(futures):
                results = future.result()
                assert all(r == expected.decision.value for r in results)

    def test_norm_shuffle_stability(self) -> None:
        """Norms loaded in random order produce the same verdict (sort stability)."""
        engine = _make_engine()
        norms = [
            NormFrame(
                code="CodeA", agent_pattern="*",
                modality=DeonticModality.FORBIDDEN,
                proposition=("act",), specificity=5, defeasible=True,
                source="norm-F-5",
            ),
            NormFrame(
                code="CodeB", agent_pattern="*",
                modality=DeonticModality.PERMITTED,
                proposition=("act",), specificity=3, defeasible=True,
                source="norm-P-3",
            ),
            NormFrame(
                code="CodeA", agent_pattern="*",
                modality=DeonticModality.PERMITTED,
                proposition=("act",), specificity=7, defeasible=True,
                source="norm-P-7",
            ),
            NormFrame(
                code="CodeB", agent_pattern="*",
                modality=DeonticModality.FORBIDDEN,
                proposition=("act",), specificity=2, defeasible=True,
                source="norm-F-2",
            ),
        ]

        canonical = engine.evaluate(("act",), "*", norms)

        for _ in range(50):
            shuffled = list(norms)
            random.shuffle(shuffled)
            result = engine.evaluate(("act",), "*", shuffled)
            assert result.modality == canonical.modality, (
                "Shuffled norms produced different modality"
            )
            assert result.reason == canonical.reason

    def test_timing_variance_bounded(self) -> None:
        """Standard deviation of check times < 5x median (no pathological cases)."""
        guard = _load_guard()
        action_types = guard._registry.action_types
        if not action_types:
            pytest.skip("No action types registered")

        action = Action(
            action_type=action_types[0],
            agent_id="test-agent",
            proposition={},
        )

        times: list[float] = []
        for _ in range(100):
            start = time.monotonic()
            guard.check(action)
            times.append(time.monotonic() - start)

        median_time = statistics.median(times)
        stdev_time = statistics.stdev(times)

        # Guard against zero median (all checks < timer resolution)
        if median_time > 0:
            assert stdev_time < 5 * median_time, (
                f"Timing variance too high: stdev={stdev_time:.6f}, "
                f"median={median_time:.6f}, ratio={stdev_time/median_time:.1f}"
            )
