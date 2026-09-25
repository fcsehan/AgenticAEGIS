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

"""DBClass — indexed fact/rule storage. Port of BPS/ftre/fdata.lisp.

The "dbclass" of an assertion is the leftmost constant symbol in the form.
DBClasses provide O(1) lookup by leading symbol, which is key to making
the pattern matcher fast enough for the <50ms budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aegis.engine.pattern_matcher import FAIL, Term, is_variable, sublis, unify


@dataclass
class DBClass:
    """Storage bin for facts and rules sharing the same leftmost constant.

    Attributes:
        name: The leading constant symbol (e.g. ``"isa"``, ``"forbiddenToDo"``).
        facts: Assertions indexed under this class.
        rules: Rules triggered by assertions of this class.
    """

    name: str
    facts: list[tuple[Any, ...]] = field(default_factory=list)
    rules: list[Any] = field(default_factory=list)


class DBClassTable:
    """Hash table of DBClasses, keyed by the leftmost constant in a term.

    Port of the ``ftre-dbclass-table`` hash-table from fdata.lisp.
    """

    def __init__(self) -> None:
        self._table: dict[str, DBClass] = {}

    def get_dbclass(self, fact: Term) -> DBClass:
        """Get (or create) the DBClass for *fact*.

        The dbclass key is the leftmost constant (non-variable) symbol.
        For a tuple, that's ``get_dbclass(fact[0])``.
        For a string atom, it's the atom itself.

        Port of ``get-dbclass`` in fdata.lisp lines 68-84.

        Raises:
            ValueError: If *fact* is None or a bare unbound variable.
        """
        if fact is None:
            raise ValueError("None cannot be a dbclass")

        if isinstance(fact, tuple):
            if not fact:
                raise ValueError("Empty tuple cannot be a dbclass")
            return self.get_dbclass(fact[0])

        if is_variable(fact):
            raise ValueError(f"Unbound variable cannot be a dbclass: {fact}")

        if isinstance(fact, str):
            if fact not in self._table:
                self._table[fact] = DBClass(name=fact)
            return self._table[fact]

        raise ValueError(f"Bad dbclass type: {fact!r}")

    def insert(self, fact: tuple[Any, ...]) -> bool:
        """Insert *fact* into the appropriate DBClass. Returns True if new.

        Idempotent: duplicate facts are ignored (as in fdata.lisp line 60-61).

        Raises:
            ValueError: If *fact* is None.
        """
        if fact is None:
            raise ValueError("Cannot assert None")
        dbclass = self.get_dbclass(fact)
        if fact in dbclass.facts:
            return False
        dbclass.facts.append(fact)
        return True

    def fetch(self, pattern: Term) -> list[Term]:
        """Find all facts matching *pattern* via unification.

        Port of ``fetch`` in fdata.lisp lines 89-95.
        """
        candidates = self._get_candidates(pattern)
        results: list[Term] = []
        for candidate in candidates:
            bindings = unify(pattern, candidate)
            if bindings is not FAIL:
                results.append(sublis(bindings, pattern))  # type: ignore[arg-type]
        return results

    def _get_candidates(self, pattern: Term) -> list[tuple[Any, ...]]:
        """Get candidate facts for *pattern*.

        Port of ``get-candidates`` in fdata.lisp lines 97-99.
        """
        try:
            dbclass = self.get_dbclass(pattern)
        except ValueError:
            return []
        return dbclass.facts

    def all_facts(self) -> list[tuple[Any, ...]]:
        """Return all facts across all DBClasses."""
        result: list[tuple[Any, ...]] = []
        for dbclass in self._table.values():
            result.extend(dbclass.facts)
        return result

    def __len__(self) -> int:
        return sum(len(db.facts) for db in self._table.values())

    def __contains__(self, fact: tuple[Any, ...]) -> bool:
        try:
            dbclass = self.get_dbclass(fact)
        except ValueError:
            return False
        return fact in dbclass.facts
