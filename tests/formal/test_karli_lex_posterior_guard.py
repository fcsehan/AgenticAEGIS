"""Olson's dynamically changing norms, end to end through Guard.check.

Schema-2 instance of Olson, Salas-Damian & Forbus, "Reasoning and Planning
with Dynamically Changing Norms" (arXiv 2605.27622), Theorem 1: a later,
subsumed obligation adds an exception to an earlier prohibition. The same
two testimonies with swapped timestamps must resolve the other way, which
shows the verdict depends on temporal order (Lex Posterior), not only on
specificity. Used as evidence in the fail-closed plan-governance paper.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision

KARLI_MELD = """\
(aegis-schema-version 2)
(case KarliPrivacyMt)

(isa shareHealthInfo MedicalActionType)
(isa shareHealthCondition MedicalActionType)

;; Time: t1 < t2 < tn (tn = time of the query)
(before t1 t2)
(before t2 tn)
(before-or-equal t1 tn)
(before-or-equal t2 tn)
(between-inclusive t1 t2 tn)

;; Behaviour and context hierarchies (first argument is the narrower one)
(behavior-subsumes shareHealthInfo shareHealthInfo)
(behavior-subsumes shareHealthCondition shareHealthCondition)
(behavior-subsumes shareHealthCondition shareHealthInfo)
(context-subsumes Family Family)
(context-subsumes Children Children)
(context-subsumes Spouse Spouse)
(context-subsumes Children Family)
(context-subsumes Spouse Family)

;; "Do not share my health information with my family."
(testimony-forbidden companion shareHealthInfo Family {t_prohibition})
;; "You must share my health conditions with my children."
(testimony-obligatory companion shareHealthCondition Children {t_obligation})

(defeasible-rule R1
  :from (testimony-obligatory ?A ?B ?Phi ?T)
  :to   (belief-obligatory ?A ?C ?Delta ?Tn)
  :when ((behavior-subsumes ?B ?C)
         (context-subsumes ?Delta ?Phi)
         (before-or-equal ?T ?Tn))
  :justification
         ((testimony-obligatory ?A ?Z ?Psi ?Tx)
          (context-subsumes ?Delta ?Psi)
          (behavior-subsumes ?B ?Z)
          (between-inclusive ?T ?Tx ?Tn))
  :defeat-mode complete)

(defeasible-rule R3
  :from (testimony-forbidden ?A ?C ?Phi ?T)
  :to   (belief-forbidden ?A ?B ?Delta ?Tn)
  :when ((behavior-subsumes ?B ?C)
         (context-subsumes ?Delta ?Phi)
         (before-or-equal ?T ?Tn))
  :justification
         ((testimony-forbidden ?A ?Z ?Psi ?Tx)
          (between-inclusive ?T ?Tx ?Tn))
  :defeat-mode partial)
"""


def _guard(tmp_path: Path, *, t_prohibition: str, t_obligation: str) -> Guard:
    meld = tmp_path / "KarliPrivacyMt.meld"
    meld.write_text(
        KARLI_MELD.format(t_prohibition=t_prohibition, t_obligation=t_obligation)
    )
    return Guard.from_meld_files([meld])


def _check(guard: Guard, behavior: str, context: str) -> Decision:
    verdict = guard.check(
        Action(
            action_type=behavior,
            agent_id="companion",
            proposition={},
            context={"ddic_context": context},
        )
    )
    return verdict.decision


@pytest.mark.parametrize(
    ("behavior", "context", "expected"),
    [
        # The later obligation carves an exception out of the prohibition.
        ("shareHealthCondition", "Children", Decision.PERMITTED),
        # Outside the exception the earlier prohibition still holds.
        ("shareHealthCondition", "Spouse", Decision.FORBIDDEN),
        ("shareHealthInfo", "Spouse", Decision.FORBIDDEN),
        ("shareHealthCondition", "Family", Decision.FORBIDDEN),
    ],
)
def test_later_obligation_defeats_earlier_prohibition(
    tmp_path: Path, behavior: str, context: str, expected: Decision
) -> None:
    guard = _guard(tmp_path, t_prohibition="t1", t_obligation="t2")
    assert _check(guard, behavior, context) == expected


def test_exception_is_partial_defeat(tmp_path: Path) -> None:
    guard = _guard(tmp_path, t_prohibition="t1", t_obligation="t2")
    verdict = guard.check(
        Action(
            action_type="shareHealthCondition",
            agent_id="companion",
            proposition={},
            context={"ddic_context": "Children"},
        )
    )
    assert any(
        entry.startswith("defeat:specific_exception:partial:R3")
        for entry in verdict.justification_chain
    )


def test_swapped_timestamps_let_the_later_prohibition_win(tmp_path: Path) -> None:
    """Same testimonies, opposite order: the verdict flips."""
    guard = _guard(tmp_path, t_prohibition="t2", t_obligation="t1")
    assert _check(guard, "shareHealthCondition", "Children") == Decision.FORBIDDEN
    assert _check(guard, "shareHealthCondition", "Spouse") == Decision.FORBIDDEN
