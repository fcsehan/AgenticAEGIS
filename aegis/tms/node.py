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

"""TMS Node — port of jtms.lisp tms-node struct.

A TmsNode represents a belief in the JTMS.  Its label is IN (believed)
or OUT (disbelieved).  Support is either a Justification or the special
marker ENABLED_ASSUMPTION.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aegis.tms.justification import Justification


class NodeLabel(Enum):
    """Belief status of a TMS node."""

    IN = "IN"
    OUT = "OUT"


class TmsNode:
    """A node in the JTMS.

    Port of ``tms-node`` struct from jtms.lisp lines 35-47.

    Attributes:
        index: Unique numeric ID within this JTMS.
        datum: External data associated with this node.
        label: Current belief status (IN or OUT).
        support: Current justification (Justification | "ENABLED_ASSUMPTION" | None).
        justs: All possible justifications for this node.
        consequences: Justifications in which this node appears as an antecedent.
        mark: Sweep algorithm marker.
        is_contradictory: Flag for contradiction nodes.
        is_assumption: Flag for assumption nodes.
        in_rules: Callbacks to fire when node goes IN.
        out_rules: Callbacks to fire when node goes OUT.
    """

    __slots__ = (
        "index",
        "datum",
        "label",
        "support",
        "justs",
        "consequences",
        "mark",
        "is_contradictory",
        "is_assumption",
        "in_rules",
        "out_rules",
    )

    def __init__(
        self,
        index: int,
        datum: Any,
        *,
        is_assumption: bool = False,
        is_contradictory: bool = False,
    ) -> None:
        self.index = index
        self.datum = datum
        self.label = NodeLabel.OUT
        self.support: Justification | str | None = None
        self.justs: list[Justification] = []
        self.consequences: list[Justification] = []
        self.mark: Any = None
        self.is_contradictory = is_contradictory
        self.is_assumption = is_assumption
        self.in_rules: list[Any] = []
        self.out_rules: list[Any] = []

    @property
    def is_in(self) -> bool:
        return self.label == NodeLabel.IN

    @property
    def is_out(self) -> bool:
        return self.label == NodeLabel.OUT

    @property
    def is_premise(self) -> bool:
        """True if this node is a premise (justified with no antecedents)."""

        if self.support is None:
            return False
        if isinstance(self.support, str):
            return False  # ENABLED_ASSUMPTION is not a premise
        return len(self.support.antecedents) == 0

    def __repr__(self) -> str:
        return f"<TmsNode {self.index}: {self.datum!r} [{self.label.value}]>"
