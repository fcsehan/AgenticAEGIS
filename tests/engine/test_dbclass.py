"""Tests for DBClass and DBClassTable (fdata.lisp port)."""

from __future__ import annotations

import pytest

from aegis.engine.dbclass import DBClass, DBClassTable


class TestDBClass:
    def test_basic(self) -> None:
        db = DBClass(name="isa")
        assert db.name == "isa"
        assert db.facts == []
        assert db.rules == []


class TestDBClassTable:
    def test_insert_and_fetch(self) -> None:
        table = DBClassTable()
        table.insert(("isa", "Dog", "Animal"))
        results = table.fetch(("isa", "?x", "Animal"))
        assert ("isa", "Dog", "Animal") in results

    def test_idempotent_insert(self) -> None:
        table = DBClassTable()
        assert table.insert(("isa", "Dog", "Animal")) is True
        assert table.insert(("isa", "Dog", "Animal")) is False
        assert len(table) == 1

    def test_get_dbclass_creates(self) -> None:
        table = DBClassTable()
        db = table.get_dbclass(("isa", "Dog", "Animal"))
        assert db.name == "isa"

    def test_get_dbclass_atom(self) -> None:
        table = DBClassTable()
        db = table.get_dbclass("isa")
        assert db.name == "isa"

    def test_get_dbclass_none_raises(self) -> None:
        table = DBClassTable()
        with pytest.raises(ValueError, match="None"):
            table.get_dbclass(None)  # type: ignore[arg-type]

    def test_get_dbclass_variable_raises(self) -> None:
        table = DBClassTable()
        with pytest.raises(ValueError, match="Unbound variable"):
            table.get_dbclass("?x")

    def test_contains(self) -> None:
        table = DBClassTable()
        table.insert(("isa", "Dog", "Animal"))
        assert ("isa", "Dog", "Animal") in table
        assert ("isa", "Cat", "Animal") not in table

    def test_all_facts(self) -> None:
        table = DBClassTable()
        table.insert(("isa", "Dog", "Animal"))
        table.insert(("genls", "Dog", "Animal"))
        facts = table.all_facts()
        assert len(facts) == 2

    def test_fetch_with_unification(self) -> None:
        table = DBClassTable()
        table.insert(("isa", "Dog", "Animal"))
        table.insert(("isa", "Cat", "Animal"))
        table.insert(("isa", "Dog", "Pet"))
        results = table.fetch(("isa", "Dog", "?type"))
        assert len(results) == 2
