"""Tests for JTMS — port of jtms.lisp."""

from __future__ import annotations

from aegis.tms.jtms import JTMS


class TestJTMS:
    def test_create_node(self) -> None:
        tms = JTMS("test")
        node = tms.create_node("A")
        assert node.datum == "A"
        assert node.is_out

    def test_justify_node_no_antecedents(self) -> None:
        """A justification with no antecedents makes node IN (premise)."""
        tms = JTMS("test")
        a = tms.create_node("A")
        tms.justify_node("axiom", a, [])
        assert a.is_in

    def test_justify_with_antecedents(self) -> None:
        """B depends on A. A is OUT → B stays OUT."""
        tms = JTMS("test")
        a = tms.create_node("A")
        b = tms.create_node("B")
        tms.justify_node("rule-1", b, [a])
        assert b.is_out  # A is OUT, so B can't be IN

    def test_assume_and_propagate(self) -> None:
        """Assuming A → B becomes IN via justification."""
        tms = JTMS("test")
        a = tms.create_node("A")
        b = tms.create_node("B")
        tms.justify_node("rule-1", b, [a])
        tms.assume_node(a)
        assert a.is_in
        assert b.is_in

    def test_retract_assumption(self) -> None:
        """Retracting A → B goes OUT."""
        tms = JTMS("test")
        a = tms.create_node("A")
        b = tms.create_node("B")
        tms.justify_node("rule-1", b, [a])
        tms.assume_node(a)
        assert b.is_in

        tms.retract_assumption(a)
        assert a.is_out
        assert b.is_out

    def test_alternative_support(self) -> None:
        """B has two justifications. Retracting one keeps B IN."""
        tms = JTMS("test")
        a = tms.create_node("A")
        c = tms.create_node("C")
        b = tms.create_node("B")
        tms.justify_node("rule-1", b, [a])
        tms.justify_node("rule-2", b, [c])

        tms.assume_node(a)
        tms.assume_node(c)
        assert b.is_in

        tms.retract_assumption(a)
        assert b.is_in  # still supported by c

    def test_chain_propagation(self) -> None:
        """A → B → C. Assuming A → all become IN."""
        tms = JTMS("test")
        a = tms.create_node("A")
        b = tms.create_node("B")
        c = tms.create_node("C")
        tms.justify_node("r1", b, [a])
        tms.justify_node("r2", c, [b])
        tms.assume_node(a)
        assert a.is_in
        assert b.is_in
        assert c.is_in

    def test_chain_retraction(self) -> None:
        """Retracting A → B and C go OUT."""
        tms = JTMS("test")
        a = tms.create_node("A")
        b = tms.create_node("B")
        c = tms.create_node("C")
        tms.justify_node("r1", b, [a])
        tms.justify_node("r2", c, [b])
        tms.assume_node(a)
        tms.retract_assumption(a)
        assert b.is_out
        assert c.is_out

    def test_contradiction_handler(self) -> None:
        """Contradiction handler is called when a contradiction node goes IN."""
        contradictions_found: list[list[object]] = []

        def handler(jtms: JTMS, contras: list[object]) -> None:
            contradictions_found.append(contras)

        tms = JTMS("test", contradiction_handler=handler)
        contra = tms.create_node("CONTRA", is_contradictory=True)
        tms.justify_node("bad-axiom", contra, [])
        assert len(contradictions_found) == 1

    def test_assumptions_of_node(self) -> None:
        tms = JTMS("test")
        a = tms.create_node("A")
        b = tms.create_node("B")
        c = tms.create_node("C")
        tms.justify_node("r1", b, [a])
        tms.justify_node("r2", c, [b])
        tms.assume_node(a)

        assumptions = tms.assumptions_of_node(c)
        assert len(assumptions) == 1
        assert assumptions[0] is a

    def test_enabled_assumptions(self) -> None:
        tms = JTMS("test")
        a = tms.create_node("A")
        b = tms.create_node("B")
        tms.assume_node(a)
        tms.assume_node(b)
        assert len(tms.enabled_assumptions()) == 2
        tms.retract_assumption(a)
        assert len(tms.enabled_assumptions()) == 1
