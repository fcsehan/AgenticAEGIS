"""Tests for the Rule Engine (frules.lisp port)."""

from __future__ import annotations

from aegis.engine.pattern_matcher import Bindings
from aegis.engine.rule_engine import Rule, RuleEngine


class TestRuleEngine:
    def test_assert_fact(self) -> None:
        engine = RuleEngine()
        assert engine.assert_fact(("isa", "Dog", "Animal")) is True
        assert engine.assert_fact(("isa", "Dog", "Animal")) is False

    def test_rule_fires_on_new_fact(self) -> None:
        engine = RuleEngine()

        def transitive_rule(bindings: Bindings) -> list[tuple[object, ...]]:
            return [("derived", bindings.get("?x", ""), bindings.get("?y", ""))]

        engine.add_rule(
            Rule(
                id=1,
                trigger_pattern=("isa", "?x", "?y"),
                body=transitive_rule,
            )
        )
        engine.assert_fact(("isa", "Dog", "Animal"))

        results = engine.query(("derived", "?a", "?b"))
        assert len(results) == 1
        assert ("derived", "Dog", "Animal") in results

    def test_termination_via_duplicate_check(self) -> None:
        """Rules that produce existing facts terminate."""
        engine = RuleEngine()

        def echo_rule(bindings: Bindings) -> list[tuple[object, ...]]:
            return [("isa", bindings.get("?x", ""), bindings.get("?y", ""))]

        engine.add_rule(
            Rule(
                id=1,
                trigger_pattern=("isa", "?x", "?y"),
                body=echo_rule,
            )
        )
        engine.assert_fact(("isa", "Dog", "Animal"))
        # Should terminate — the echo_rule produces the same fact
        assert engine.fact_count >= 1

    def test_chained_rules(self) -> None:
        """Rules can chain: A triggers B triggers C."""
        engine = RuleEngine()

        def step1(b: Bindings) -> list[tuple[object, ...]]:
            return [("step2", b.get("?x", ""))]

        def step2(b: Bindings) -> list[tuple[object, ...]]:
            return [("step3", b.get("?x", ""))]

        engine.add_rule(Rule(1, ("step1", "?x"), step1))
        engine.add_rule(Rule(2, ("step2", "?x"), step2))
        engine.assert_fact(("step1", "hello"))

        assert ("step3", "hello") in engine.db
