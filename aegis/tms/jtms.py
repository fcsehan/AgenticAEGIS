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

"""JTMS — Justification-based Truth Maintenance System.

Port of Forbus & de Kleer's jtms.lisp (400 lines, Version 176).
This is the most algorithmic piece of the AEGIS engine.

Key operations:
- create_node: Add a belief node
- justify_node: Provide a justification (may trigger propagation)
- assume_node: Convert a node to an assumption and enable it
- retract_assumption: Disable an assumption and propagate outness

Per D-005: JTMS instances are per-request (no shared mutable state).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from aegis.tms.justification import Justification
from aegis.tms.node import NodeLabel, TmsNode

# Marker for enabled assumptions
ENABLED_ASSUMPTION = "ENABLED_ASSUMPTION"


class JTMS:
    """Justification-based Truth Maintenance System.

    Port of ``create-jtms`` and the JTMS struct from jtms.lisp lines 17-29.

    Usage::

        tms = JTMS("example")
        a = tms.create_node("A")
        b = tms.create_node("B")
        tms.justify_node("rule-1", b, [a])  # B is justified by A
        tms.assume_node(a)  # A is now IN → B propagates to IN
    """

    def __init__(
        self,
        title: str = "JTMS",
        *,
        checking_contradictions: bool = True,
        contradiction_handler: Callable[[JTMS, list[TmsNode]], None] | None = None,
        enqueue_procedure: Callable[[Any], None] | None = None,
    ) -> None:
        self.title = title
        self._node_counter = 0
        self._just_counter = 0
        self._nodes: list[TmsNode] = []
        self._justs: list[Justification] = []
        self._contradictions: list[TmsNode] = []
        self._assumptions: list[TmsNode] = []
        self._checking_contradictions = checking_contradictions
        self._contradiction_handler = contradiction_handler
        self._enqueue_procedure = enqueue_procedure

    # ── Node creation (jtms.lisp lines 113-122) ─────────────────────

    def create_node(
        self,
        datum: Any,
        *,
        is_assumption: bool = False,
        is_contradictory: bool = False,
    ) -> TmsNode:
        """Create a new TMS node."""
        self._node_counter += 1
        node = TmsNode(
            index=self._node_counter,
            datum=datum,
            is_assumption=is_assumption,
            is_contradictory=is_contradictory,
        )
        if is_assumption:
            self._assumptions.append(node)
        if is_contradictory:
            self._contradictions.append(node)
        self._nodes.append(node)
        return node

    # ── Justify (jtms.lisp lines 137-154) ────────────────────────────

    def justify_node(
        self, informant: str, consequence: TmsNode, antecedents: list[TmsNode]
    ) -> Justification:
        """Provide a justification for *consequence*.

        If the justification is satisfied (all antecedents IN) and the
        consequence is OUT, the consequence becomes IN and inness propagates.
        """
        self._just_counter += 1
        just = Justification(
            index=self._just_counter,
            informant=informant,
            consequence=consequence,
            antecedents=antecedents,
        )

        consequence.justs.append(just)
        for node in antecedents:
            node.consequences.append(just)
        self._justs.append(just)

        # Lines 151-153: decide whether to install support
        if antecedents or consequence.is_out:
            if self._check_justification(just):
                self._install_support(consequence, just)
        else:
            # No antecedents AND consequence is already IN → just record support
            consequence.support = just

        self._check_for_contradictions()
        return just

    # ── Assumption management (jtms.lisp lines 125-129, 195-211) ─────

    def assume_node(self, node: TmsNode) -> None:
        """Convert *node* to an assumption and enable it.

        Port of ``assume-node`` (jtms.lisp lines 125-129).
        """
        if not node.is_assumption:
            node.is_assumption = True
            self._assumptions.append(node)
        self._enable_assumption(node)

    def retract_assumption(self, node: TmsNode) -> None:
        """Retract an enabled assumption.

        Port of ``retract-assumption`` (jtms.lisp lines 195-200).
        """
        if node.support != ENABLED_ASSUMPTION:
            return

        self._make_node_out(node)
        out_queue = self._propagate_outness(node)
        self._find_alternative_support(out_queue + [node])

    def _enable_assumption(self, node: TmsNode) -> None:
        """Enable an assumption node.

        Port of ``enable-assumption`` (jtms.lisp lines 202-211).
        """
        if not node.is_assumption:
            raise ValueError(f"Cannot enable non-assumption: {node}")

        if node.is_out:
            self._make_node_in(node, ENABLED_ASSUMPTION)
            self._propagate_inness(node)
        elif node.support == ENABLED_ASSUMPTION:
            pass  # already enabled
        elif isinstance(node.support, Justification) and not node.support.antecedents:
            pass  # premise — leave as is
        else:
            node.support = ENABLED_ASSUMPTION

        self._check_for_contradictions()

    # ── Propagation (jtms.lisp lines 169-246) ────────────────────────

    def _propagate_inness(self, node: TmsNode) -> None:
        """BFS propagation of belief. Port of jtms.lisp lines 169-175."""
        queue: deque[TmsNode] = deque([node])

        while queue:
            current = queue.popleft()
            for just in current.consequences:
                if self._check_justification(just):
                    self._make_node_in(just.consequence, just)
                    queue.append(just.consequence)

    def _propagate_outness(self, node: TmsNode) -> list[TmsNode]:
        """Propagate disbelief. Port of jtms.lisp lines 223-236.

        Returns the list of nodes that went OUT.
        """
        out_queue: list[TmsNode] = []
        # BFS through consequences
        to_check: deque[Justification] = deque(node.consequences)

        while to_check:
            just = to_check.popleft()
            conseq = just.consequence
            # Only propagate if this justification was the active support
            if conseq.support is just:
                self._make_node_out(conseq)
                out_queue.append(conseq)
                to_check.extend(conseq.consequences)

        return out_queue

    def _find_alternative_support(self, out_queue: list[TmsNode]) -> None:
        """Try to find alternative justifications for OUT nodes.

        Port of jtms.lisp lines 238-246.
        """
        for node in out_queue:
            if node.is_in:
                continue
            for just in node.justs:
                if self._check_justification(just):
                    self._install_support(just.consequence, just)
                    break

    # ── Support helpers (jtms.lisp lines 158-192) ────────────────────

    @staticmethod
    def _check_justification(just: Justification) -> bool:
        """True if the justification is satisfied and consequence is OUT.

        Port of ``check-justification`` (jtms.lisp lines 158-160).
        """
        return just.consequence.is_out and just.is_satisfied()

    def _install_support(self, conseq: TmsNode, just: Justification) -> None:
        """Make *conseq* IN via *just* and propagate.

        Port of ``install-support`` (jtms.lisp lines 165-167).
        """
        self._make_node_in(conseq, just)
        self._propagate_inness(conseq)

    def _make_node_in(self, node: TmsNode, reason: Justification | str) -> None:
        """Set *node* to IN with *reason* as support.

        Port of ``make-node-in`` (jtms.lisp lines 177-192).
        """
        node.label = NodeLabel.IN
        node.support = reason
        if self._enqueue_procedure:
            for rule in node.in_rules:
                self._enqueue_procedure(rule)
            node.in_rules.clear()

    def _make_node_out(self, node: TmsNode) -> None:
        """Set *node* to OUT. Port of ``make-node-out`` (jtms.lisp lines 213-221)."""
        node.support = None
        node.label = NodeLabel.OUT
        if self._enqueue_procedure:
            for rule in node.out_rules:
                self._enqueue_procedure(rule)
            node.out_rules.clear()

    # ── Contradiction handling (jtms.lisp lines 249-254) ─────────────

    def _check_for_contradictions(self) -> None:
        """Check for contradictions and call handler if found."""
        if not self._checking_contradictions:
            return
        in_contras = [n for n in self._contradictions if n.is_in]
        if in_contras and self._contradiction_handler:
            self._contradiction_handler(self, in_contras)

    def make_contradiction(self, node: TmsNode) -> None:
        """Mark *node* as contradictory. Port of jtms.lisp lines 131-135."""
        if not node.is_contradictory:
            node.is_contradictory = True
            self._contradictions.append(node)
            self._check_for_contradictions()

    # ── Inquiry (jtms.lisp lines 289-307) ────────────────────────────

    def assumptions_of_node(self, node: TmsNode) -> list[TmsNode]:
        """Trace back to find all assumptions supporting *node*.

        Port of ``assumptions-of-node`` (jtms.lisp lines 292-302).
        """
        assumptions: list[TmsNode] = []
        marker = object()
        queue: deque[TmsNode] = deque([node])

        while queue:
            current = queue.popleft()
            if current.mark is marker:
                continue
            current.mark = marker
            if current.support == ENABLED_ASSUMPTION:
                assumptions.append(current)
            elif current.is_in and isinstance(current.support, Justification):
                queue.extend(current.support.antecedents)

        return assumptions

    def enabled_assumptions(self) -> list[TmsNode]:
        """Return all currently enabled assumptions."""
        return [a for a in self._assumptions if a.support == ENABLED_ASSUMPTION]

    # ── Accessors ────────────────────────────────────────────────────

    @property
    def nodes(self) -> list[TmsNode]:
        return list(self._nodes)

    @property
    def justifications(self) -> list[Justification]:
        return list(self._justs)

    def __repr__(self) -> str:
        return f"<JTMS: {self.title}>"
