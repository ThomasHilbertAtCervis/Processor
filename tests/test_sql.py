"""Tiny SQL-ish DSL: tokeniser, parser, placeholder discovery, evaluator."""
from __future__ import annotations

import pytest

from processor_playground import sql


# ----------------------------------------------------------------- SELECT

def test_select_star_without_where() -> None:
    stmt = sql.parse("SELECT * FROM customer")
    assert isinstance(stmt, sql.SelectStmt)
    assert stmt.table == "customer"
    assert stmt.where == []
    assert sql.placeholder_names(stmt) == []


def test_select_with_where_and_placeholders() -> None:
    stmt = sql.parse("SELECT * FROM customer WHERE region = :region AND age > :min_age")
    assert isinstance(stmt, sql.SelectStmt)
    assert stmt.table == "customer"
    assert len(stmt.where) == 2
    assert stmt.where[0].column == "region"
    assert stmt.where[0].op == "="
    assert isinstance(stmt.where[0].value, sql.Placeholder)
    assert stmt.where[0].value.name == "region"
    assert sql.placeholder_names(stmt) == ["region", "min_age"]


def test_select_with_literal_value() -> None:
    stmt = sql.parse("SELECT * FROM x WHERE n >= 18")
    assert stmt.where[0].value == 18
    assert sql.placeholder_names(stmt) == []


def test_select_with_string_literal() -> None:
    stmt = sql.parse("SELECT * FROM x WHERE name = 'alice'")
    assert stmt.where[0].value == "alice"


# ----------------------------------------------------------------- INSERT

def test_insert_columns_and_values() -> None:
    stmt = sql.parse("INSERT INTO customer (name, age) VALUES (:name, :age)")
    assert isinstance(stmt, sql.InsertStmt)
    assert stmt.table == "customer"
    assert stmt.columns == ["name", "age"]
    assert [v.name for v in stmt.values] == ["name", "age"]  # type: ignore[union-attr]
    assert sql.placeholder_names(stmt) == ["name", "age"]


def test_insert_with_literal_values() -> None:
    stmt = sql.parse("INSERT INTO x (a, b) VALUES (1, 'hi')")
    assert sql.placeholder_names(stmt) == []
    assert stmt.values == [1, "hi"]


def test_insert_column_value_count_mismatch_is_error() -> None:
    with pytest.raises(ValueError):
        sql.parse("INSERT INTO x (a, b) VALUES (1)")


# ----------------------------------------------------------------- errors

@pytest.mark.parametrize(
    "bad",
    [
        "DELETE FROM x",         # unsupported
        "SELECT a FROM x",       # only SELECT * supported
        "SELECT * FROM",          # missing table
        "SELECT * FROM x WHERE", # missing condition
        "INSERT INTO x VALUES (1)",  # missing column list
        "garbage",
    ],
)
def test_invalid_queries_raise(bad: str) -> None:
    with pytest.raises(ValueError):
        sql.parse(bad)


# ----------------------------------------------------------------- execute

def test_execute_select_filters_rows() -> None:
    stmt = sql.parse("SELECT * FROM x WHERE region = :r")
    rows = [
        {"id": 1, "region": "EU"},
        {"id": 2, "region": "US"},
        {"id": 3, "region": "EU"},
    ]
    out = sql.execute(stmt, table_rows=rows, params={"r": "EU"})
    assert [row["id"] for row in out] == [1, 3]


def test_execute_select_without_where_returns_all() -> None:
    stmt = sql.parse("SELECT * FROM x")
    rows = [{"id": 1}, {"id": 2}]
    out = sql.execute(stmt, table_rows=rows, params={})
    assert out == rows
    assert out is not rows  # shallow copy


def test_execute_insert_appends_row_and_returns_it() -> None:
    stmt = sql.parse("INSERT INTO x (name, age) VALUES (:n, :a)")
    rows: list[dict] = []
    inserted = sql.execute(stmt, table_rows=rows, params={"n": "alice", "a": 30})
    assert inserted == {"name": "alice", "age": 30}
    assert rows == [{"name": "alice", "age": 30}]


def test_execute_missing_placeholder_raises() -> None:
    stmt = sql.parse("SELECT * FROM x WHERE a = :missing")
    with pytest.raises(KeyError):
        sql.execute(stmt, table_rows=[{"a": 1}], params={})
