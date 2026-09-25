# Python adaptation for AEGIS; see THIRD_PARTY_NOTICES.md.
# Copyright (c) 1986-1993 Kenneth D. Forbus, Johan de Kleer and Xerox
# Corporation.  All Rights Reserved.
#
# Use, reproduction, and preparation of derivative works are permitted.
# Any copy of this software or of any derivative work must include the
# above copyright notice and this paragraph.  Any distribution of this
# software or derivative works must comply with all applicable United
# States export control laws.  This software is made available as is, and
# Kenneth D. Forbus, Johan de Kleer and Xerox Corporation disclaim all
# warranties, express or implied, including without limitation the implied
# warranties of merchantability and fitness for a particular purpose, and
# notwithstanding any other provision contained herein, any liability for
# damages resulting from the software or its use is expressly disclaimed,
# whether arising in contract, tort (including negligence) or strict
# liability, even if Kenneth D. Forbus, Johan de Kleer or Xerox
# Corporation is advised of the possibility of such damages.

"""Rule Engine — port of BPS/ftre/frules.lisp.

Forward-chaining rule engine.  When a fact is asserted, matching rules fire
and may assert new facts (which may trigger more rules).

Termination is guaranteed by the duplicate-check on facts: a fact is only
asserted once, and only new facts trigger rules.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aegis.engine.dbclass import DBClassTable
from aegis.engine.pattern_matcher import FAIL, Bindings, Term, unify


@dataclass(frozen=True, slots=True)
class Rule:
    """A forward-chaining rule.

    Attributes:
        id: Unique rule identifier.
        trigger_pattern: Pattern that triggers this rule when a matching fact arrives.
        body: Callable that receives bindings and produces new facts.
        assumption: If True, this rule produces assumptions (lower priority).
    """

    id: int
    trigger_pattern: tuple[Any, ...]
    body: Callable[[Bindings], list[tuple[Any, ...]]]
    assumption: bool = False


class RuleEngine:
    """Forward-chaining inference engine.

    Port of the FTRE rule engine from frules.lisp.  Uses a priority queue
    where normal rules fire before assumption rules.

    Usage::

        engine = RuleEngine()
        engine.add_rule(Rule(1, ("parent", "?x", "?y"), grandparent_rule))
        engine.assert_fact(("parent", "Alice", "Bob"))
        # Rules fire, may assert new facts transitively.
    """

    def __init__(self) -> None:
        self._db = DBClassTable()
        self._rules: list[Rule] = []
        self._rule_counter = 0
        # Two queues: normal fires before assumptions (frules.lisp enqueue/dequeue)
        self._normal_queue: deque[tuple[Callable[..., Any], Bindings]] = deque()
        self._assumption_queue: deque[tuple[Callable[..., Any], Bindings]] = deque()

    @property
    def db(self) -> DBClassTable:
        return self._db

    def add_rule(self, rule: Rule) -> None:
        """Register a rule.  It immediately tries against all existing facts."""
        self._rules.append(rule)
        # Try against existing facts (frules.lisp insert-rule lines 229-231)
        dbclass = self._db.get_dbclass(rule.trigger_pattern)
        for candidate in dbclass.facts:
            self._try_rule_on(rule, candidate)
        self._run_rules()

    def assert_fact(self, fact: tuple[Any, ...]) -> bool:
        """Assert *fact*. If new, triggers matching rules.

        Returns True if the fact was new.
        """
        if not self._db.insert(fact):
            return False
        self._try_rules(fact)
        self._run_rules()
        return True

    def query(self, pattern: Term) -> list[Term]:
        """Find facts matching *pattern*."""
        return self._db.fetch(pattern)

    def _try_rules(self, fact: tuple[Any, ...]) -> None:
        """Try all rules against *fact*. Port of try-rules (frules.lisp 233-235)."""
        dbclass = self._db.get_dbclass(fact)
        for rule in self._rules:
            if self._db.get_dbclass(rule.trigger_pattern).name == dbclass.name:
                self._try_rule_on(rule, fact)

    def _try_rule_on(self, rule: Rule, fact: tuple[Any, ...]) -> None:
        """Try to match *rule* against *fact*. Enqueue body if match succeeds."""
        bindings = unify(rule.trigger_pattern, fact)
        if bindings is not FAIL:
            assert isinstance(bindings, dict)
            if rule.assumption:
                self._assumption_queue.append((rule.body, bindings))
            else:
                self._normal_queue.append((rule.body, bindings))

    def _run_rules(self) -> None:
        """Execute queued rule bodies. Normal queue drains before assumptions.

        Port of run-rules (frules.lisp 249-257) + dequeue (lines 263-266).
        """
        iterations = 0
        max_iterations = 10_000  # safety limit

        while iterations < max_iterations:
            if self._normal_queue:
                body, bindings = self._normal_queue.popleft()
            elif self._assumption_queue:
                body, bindings = self._assumption_queue.popleft()
            else:
                break

            new_facts = body(bindings)
            for nf in new_facts:
                if self._db.insert(nf):
                    self._try_rules(nf)
            iterations += 1

    @property
    def fact_count(self) -> int:
        return len(self._db)
