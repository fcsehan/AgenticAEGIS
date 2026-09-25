"""Tests for the pattern matcher (unify.lisp port)."""

from __future__ import annotations

from aegis.engine.pattern_matcher import FAIL, fetch, is_variable, occurs_in, sublis, unify


class TestIsVariable:
    def test_variable(self) -> None:
        assert is_variable("?x")

    def test_not_variable_no_prefix(self) -> None:
        assert not is_variable("x")

    def test_not_variable_number(self) -> None:
        assert not is_variable(42)

    def test_not_variable_single_char(self) -> None:
        assert not is_variable("?")


class TestUnify:
    def test_identical_atoms(self) -> None:
        assert unify("a", "a") == {}

    def test_different_atoms_fail(self) -> None:
        assert unify("a", "b") is FAIL

    def test_variable_binds(self) -> None:
        result = unify("?x", "a")
        assert result == {"?x": "a"}

    def test_two_variables(self) -> None:
        result = unify("?x", "?y")
        assert result is not FAIL
        assert isinstance(result, dict)

    def test_tuple_unification(self) -> None:
        result = unify(("isa", "?x", "Animal"), ("isa", "Dog", "Animal"))
        assert result == {"?x": "Dog"}

    def test_nested_tuples(self) -> None:
        result = unify(
            ("isa", ("fn", "?x"), "Type"),
            ("isa", ("fn", "a"), "Type"),
        )
        assert result == {"?x": "a"}

    def test_mismatched_tuples_fail(self) -> None:
        assert unify(("a", "b"), ("a", "c")) is FAIL

    def test_different_length_fail(self) -> None:
        assert unify(("a", "b"), ("a", "b", "c")) is FAIL

    def test_occurs_check(self) -> None:
        # ?x cannot unify with a term containing ?x
        assert unify("?x", ("f", "?x")) is FAIL

    def test_transitive_binding(self) -> None:
        result = unify("?x", "?y", {"?y": "a"})
        assert result is not FAIL
        assert isinstance(result, dict)
        # ?x binds to ?y (which is already bound to "a")
        # Full resolution happens via sublis
        assert sublis(result, "?x") == "a"


class TestOccursIn:
    def test_direct(self) -> None:
        assert occurs_in("?x", "?x", {})

    def test_in_tuple(self) -> None:
        assert occurs_in("?x", ("f", "?x"), {})

    def test_not_in(self) -> None:
        assert not occurs_in("?x", ("f", "?y"), {})

    def test_through_binding(self) -> None:
        assert occurs_in("?x", "?y", {"?y": ("f", "?x")})


class TestSublis:
    def test_substitute_variable(self) -> None:
        assert sublis({"?x": "a"}, "?x") == "a"

    def test_substitute_in_tuple(self) -> None:
        assert sublis({"?x": "Dog"}, ("isa", "?x", "Animal")) == ("isa", "Dog", "Animal")

    def test_no_substitution(self) -> None:
        assert sublis({}, ("isa", "Dog", "Animal")) == ("isa", "Dog", "Animal")

    def test_transitive(self) -> None:
        assert sublis({"?x": "?y", "?y": "a"}, "?x") == "a"


class TestFetch:
    def test_fetch_matches(self) -> None:
        facts = [
            ("isa", "Dog", "Animal"),
            ("isa", "Cat", "Animal"),
            ("genls", "Dog", "Animal"),
        ]
        results = fetch(("isa", "?x", "Animal"), facts)
        assert len(results) == 2
        assert ("isa", "Dog", "Animal") in results
        assert ("isa", "Cat", "Animal") in results

    def test_fetch_no_match(self) -> None:
        facts = [("isa", "Dog", "Animal")]
        results = fetch(("genls", "?x", "?y"), facts)
        assert results == []


# ── DDICTerm Unification ────────────────────────────────────────────

from aegis.engine.ddic_ir import DDICCompound, DDICInteger, DDICSymbol, DDICVar
from aegis.engine.pattern_matcher import proposition_to_term, unify_terms


class TestUnifyTermsBasic:
    def test_identical_symbols(self) -> None:
        assert unify_terms(DDICSymbol("a"), DDICSymbol("a")) == {}

    def test_different_symbols_fail(self) -> None:
        assert unify_terms(DDICSymbol("a"), DDICSymbol("b")) is FAIL

    def test_identical_integers(self) -> None:
        assert unify_terms(DDICInteger(42), DDICInteger(42)) == {}

    def test_different_integers_fail(self) -> None:
        assert unify_terms(DDICInteger(1), DDICInteger(2)) is FAIL

    def test_symbol_vs_integer_fail(self) -> None:
        assert unify_terms(DDICSymbol("1"), DDICInteger(1)) is FAIL

    def test_identical_compounds(self) -> None:
        a = DDICCompound("f", (DDICSymbol("x"),))
        assert unify_terms(a, a) == {}

    def test_compound_head_mismatch(self) -> None:
        a = DDICCompound("f", (DDICSymbol("x"),))
        b = DDICCompound("g", (DDICSymbol("x"),))
        assert unify_terms(a, b) is FAIL

    def test_compound_arg_mismatch(self) -> None:
        a = DDICCompound("f", (DDICSymbol("x"),))
        b = DDICCompound("f", (DDICSymbol("y"),))
        assert unify_terms(a, b) is FAIL

    def test_compound_length_mismatch(self) -> None:
        a = DDICCompound("f", (DDICSymbol("x"),))
        b = DDICCompound("f", (DDICSymbol("x"), DDICSymbol("y")))
        assert unify_terms(a, b) is FAIL

    def test_nested_compound(self) -> None:
        inner = DDICCompound("g", (DDICSymbol("a"),))
        a = DDICCompound("f", (inner,))
        b = DDICCompound("f", (inner,))
        assert unify_terms(a, b) == {}


class TestUnifyTermsVariables:
    def test_var_binds(self) -> None:
        result = unify_terms(DDICVar("?x"), DDICSymbol("hello"))
        assert result == {"?x": DDICSymbol("hello")}

    def test_var_consistency(self) -> None:
        a = DDICCompound("f", (DDICVar("?x"), DDICVar("?x")))
        b = DDICCompound("f", (DDICSymbol("a"), DDICSymbol("a")))
        result = unify_terms(a, b)
        assert result is not FAIL
        assert result["?x"] == DDICSymbol("a")

    def test_var_inconsistency_fail(self) -> None:
        a = DDICCompound("f", (DDICVar("?x"), DDICVar("?x")))
        b = DDICCompound("f", (DDICSymbol("a"), DDICSymbol("b")))
        assert unify_terms(a, b) is FAIL

    def test_var_on_right(self) -> None:
        result = unify_terms(DDICSymbol("a"), DDICVar("?y"))
        assert result == {"?y": DDICSymbol("a")}


class TestUnifyTermsPrefix:
    def test_prefix_shorter_pattern(self) -> None:
        a = DDICCompound("share", (DDICSymbol("classified"),))
        b = DDICCompound("share", (DDICSymbol("classified"), DDICSymbol("ext")))
        # Without prefix: FAIL (different arg count)
        assert unify_terms(a, b) is FAIL
        # With prefix: match
        assert unify_terms(a, b, prefix=True) is not FAIL

    def test_prefix_symbol_matches_compound_head(self) -> None:
        a = DDICSymbol("share")
        b = DDICCompound("share", (DDICSymbol("classified"),))
        assert unify_terms(a, b) is FAIL
        assert unify_terms(a, b, prefix=True) is not FAIL

    def test_prefix_head_mismatch(self) -> None:
        a = DDICSymbol("send")
        b = DDICCompound("share", (DDICSymbol("x"),))
        assert unify_terms(a, b, prefix=True) is FAIL


class TestPropositionToTerm:
    def test_single(self) -> None:
        result = proposition_to_term(("doThing",))
        assert result == DDICSymbol("doThing")

    def test_compound(self) -> None:
        result = proposition_to_term(("share", "classified", "ext"))
        expected = DDICCompound("share", (DDICSymbol("classified"), DDICSymbol("ext")))
        assert result == expected
