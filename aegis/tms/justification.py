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

"""Justification — port of jtms.lisp just struct.

A Justification records why a node is believed: an informant (reason label),
a consequence (the justified node), and antecedents (supporting nodes).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aegis.tms.node import TmsNode


class Justification:
    """A justification for a TMS node.

    Port of ``just`` struct from jtms.lisp lines 53-57.

    Attributes:
        index: Unique numeric ID.
        informant: Label describing the source of this justification.
        consequence: The node being justified.
        antecedents: Nodes that must be IN for this justification to hold.
    """

    __slots__ = ("index", "informant", "consequence", "antecedents")

    def __init__(
        self,
        index: int,
        informant: str,
        consequence: TmsNode,
        antecedents: list[TmsNode],
    ) -> None:
        self.index = index
        self.informant = informant
        self.consequence = consequence
        self.antecedents = antecedents

    def is_satisfied(self) -> bool:
        """True if all antecedents are IN."""
        return all(node.is_in for node in self.antecedents)

    def __repr__(self) -> str:
        return f"<Just {self.index}: {self.informant}>"
