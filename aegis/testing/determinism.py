"""AEGIS-1101: Determinism Checker.

Verifies that Guard.check() is deterministic: identical input → identical output,
every time. This is Invariant I1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Verdict


@dataclass
class DeterminismResult:
    """Result of a determinism check.

    Attributes:
        action: The action that was checked.
        runs: Number of runs performed.
        deterministic: True if all runs produced identical results.
        first_divergence: Run index where results first diverged (None if deterministic).
        diff: Description of the first divergence (empty if deterministic).
    """

    action: Action
    runs: int
    deterministic: bool
    first_divergence: int | None = None
    diff: list[str] = field(default_factory=list)


class DeterminismChecker:
    """Checks that Guard.check() is deterministic (I1).

    Usage::

        checker = DeterminismChecker(guard)
        result = checker.verify(action, n=100)
        assert result.deterministic
    """

    def __init__(self, guard: Guard) -> None:
        self._guard = guard

    def verify(self, action: Action, n: int = 100) -> DeterminismResult:
        """Run Guard.check(action) n times and verify all results are identical."""
        if n < 2:
            raise ValueError("n must be >= 2")

        reference = self._guard.check(action)
        for i in range(1, n):
            current = self._guard.check(action)
            diffs = _diff_verdicts(reference, current)
            if diffs:
                return DeterminismResult(
                    action=action,
                    runs=i + 1,
                    deterministic=False,
                    first_divergence=i,
                    diff=diffs,
                )

        return DeterminismResult(
            action=action,
            runs=n,
            deterministic=True,
        )

    def verify_batch(
        self, actions: list[Action], n: int = 100
    ) -> list[DeterminismResult]:
        """Verify determinism for multiple actions."""
        return [self.verify(action, n) for action in actions]


def _diff_verdicts(a: Verdict, b: Verdict) -> list[str]:
    """Compare two verdicts and return a list of differences."""
    diffs: list[str] = []
    if a.decision != b.decision:
        diffs.append(f"decision: {a.decision.value} vs {b.decision.value}")
    if a.reason_type != b.reason_type:
        diffs.append(f"reason_type: {a.reason_type.value} vs {b.reason_type.value}")
    if a.norms_applied != b.norms_applied:
        diffs.append(f"norms_applied: {a.norms_applied} vs {b.norms_applied}")
    if a.justification_chain != b.justification_chain:
        diffs.append(
            f"justification_chain: {a.justification_chain} vs {b.justification_chain}"
        )
    return diffs
