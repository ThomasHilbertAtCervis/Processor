"""Minimal SQL-ish parser + evaluator for the ``db_read`` / ``db_create``
node kinds.

Deliberately *not* a real SQL implementation — it supports just enough to
express the two CRUD operations shipping in v1:

* ``SELECT * FROM <table> [WHERE <conditions>]``
* ``INSERT INTO <table> (col, ...) VALUES (value, ...)``

Values inside ``WHERE`` and ``VALUES`` are either literals
(``int``/``float``/``string``/``true``/``false``/``null``) or
``:placeholder`` references. Each unique placeholder becomes one input
port on the owning node; literals do not.

The evaluator works against an in-memory ``DatabaseState``
(``{table_name: [row_dict, ...]}``) and never touches disk.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal


# --------------------------------------------------------------- AST

ComparisonOp = Literal["=", "!=", "<", "<=", ">", ">="]


@dataclass
class Placeholder:
    name: str


# A value in a WHERE/VALUES clause: either a Python literal or a placeholder.
Value = Any | Placeholder


@dataclass
class Condition:
    column: str
    op: ComparisonOp
    value: Value


@dataclass
class SelectStmt:
    table: str
    where: list[Condition] = field(default_factory=list)


@dataclass
class InsertStmt:
    table: str
    columns: list[str]
    values: list[Value]


Statement = SelectStmt | InsertStmt


# --------------------------------------------------------------- tokenizer

_TOKEN_RE = re.compile(
    r"""
      \s+                            # whitespace (skipped)
    | (?P<num>-?\d+(?:\.\d+)?)       # integer / float literal
    | (?P<str>'(?:[^'\\]|\\.)*'      # 'single' or "double" string literal
            |"(?:[^"\\]|\\.)*")
    | (?P<ph>:[A-Za-z_][A-Za-z_0-9]*) # :placeholder
    | (?P<op>!=|<=|>=|=|<|>)         # comparison operator
    | (?P<punct>[(),*])              # punctuation
    | (?P<word>[A-Za-z_][A-Za-z_0-9]*) # identifier or keyword
    """,
    re.VERBOSE,
)


def _tokenize(source: str) -> list[tuple[str, str]]:
    """Return a list of ``(kind, text)`` tokens. Raises ``ValueError`` on
    an unrecognised character."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(source):
        match = _TOKEN_RE.match(source, pos)
        if not match:
            raise ValueError(
                f"Unexpected character at position {pos}: {source[pos]!r}"
            )
        pos = match.end()
        kind = match.lastgroup
        if kind is None:  # whitespace
            continue
        tokens.append((kind, match.group()))
    return tokens


# --------------------------------------------------------------- parser


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _eat(self, kind: str | None = None, text: str | None = None) -> tuple[str, str]:
        token = self._peek()
        if token is None:
            raise ValueError("Unexpected end of input")
        if kind is not None and token[0] != kind:
            raise ValueError(f"Expected {kind}, got {token[0]} ({token[1]!r})")
        if text is not None and token[1].upper() != text.upper():
            raise ValueError(f"Expected {text!r}, got {token[1]!r}")
        self.pos += 1
        return token

    def _eat_keyword(self, word: str) -> None:
        token = self._eat("word")
        if token[1].upper() != word.upper():
            raise ValueError(f"Expected keyword {word!r}, got {token[1]!r}")

    def _parse_value(self) -> Value:
        token = self._peek()
        if token is None:
            raise ValueError("Expected a value")
        kind, text = token
        if kind == "ph":
            self.pos += 1
            return Placeholder(text[1:])
        if kind == "num":
            self.pos += 1
            return float(text) if "." in text else int(text)
        if kind == "str":
            self.pos += 1
            quote = text[0]
            inner = text[1:-1].replace(f"\\{quote}", quote)
            return inner
        if kind == "word" and text.upper() in {"TRUE", "FALSE", "NULL"}:
            self.pos += 1
            return {"TRUE": True, "FALSE": False, "NULL": None}[text.upper()]
        raise ValueError(f"Expected a value, got {text!r}")

    def parse(self) -> Statement:
        first = self._peek()
        if first is None or first[0] != "word":
            raise ValueError("Statement must start with SELECT or INSERT")
        keyword = first[1].upper()
        if keyword == "SELECT":
            return self._parse_select()
        if keyword == "INSERT":
            return self._parse_insert()
        raise ValueError(
            f"Unsupported statement {keyword!r}. Only SELECT and INSERT are "
            "supported in v1."
        )

    def _parse_select(self) -> SelectStmt:
        self._eat_keyword("SELECT")
        # Only ``SELECT *`` is supported in v1 — the row shape is fully
        # determined by the table's data type, so column projection adds
        # no expressiveness yet.
        star = self._eat()
        if star[0] != "punct" or star[1] != "*":
            raise ValueError("Only 'SELECT *' is supported in v1")
        self._eat_keyword("FROM")
        table = self._eat("word")[1]
        where: list[Condition] = []
        if self._peek() and self._peek()[0] == "word" and self._peek()[1].upper() == "WHERE":
            self._eat_keyword("WHERE")
            where.append(self._parse_condition())
            while self._peek() and self._peek()[0] == "word" and self._peek()[1].upper() == "AND":
                self._eat_keyword("AND")
                where.append(self._parse_condition())
        self._expect_end()
        return SelectStmt(table=table, where=where)

    def _parse_condition(self) -> Condition:
        column = self._eat("word")[1]
        op_tok = self._eat("op")[1]
        value = self._parse_value()
        return Condition(column=column, op=op_tok, value=value)

    def _parse_insert(self) -> InsertStmt:
        self._eat_keyword("INSERT")
        self._eat_keyword("INTO")
        table = self._eat("word")[1]
        self._eat("punct", "(")
        columns = [self._eat("word")[1]]
        while self._peek() and self._peek() == ("punct", ","):
            self.pos += 1
            columns.append(self._eat("word")[1])
        self._eat("punct", ")")
        self._eat_keyword("VALUES")
        self._eat("punct", "(")
        values: list[Value] = [self._parse_value()]
        while self._peek() and self._peek() == ("punct", ","):
            self.pos += 1
            values.append(self._parse_value())
        self._eat("punct", ")")
        if len(columns) != len(values):
            raise ValueError(
                f"INSERT column count ({len(columns)}) does not match value "
                f"count ({len(values)})"
            )
        self._expect_end()
        return InsertStmt(table=table, columns=columns, values=values)

    def _expect_end(self) -> None:
        if self.pos < len(self.tokens):
            extra = self.tokens[self.pos]
            raise ValueError(f"Unexpected trailing token: {extra[1]!r}")


def parse(source: str) -> Statement:
    """Parse a SELECT or INSERT statement. Raises ``ValueError`` on any
    syntax error or unsupported feature."""
    return _Parser(_tokenize(source)).parse()


# --------------------------------------------------------------- placeholders


def placeholder_names(stmt: Statement) -> list[str]:
    """Return the ordered, de-duplicated list of placeholder names referenced
    by ``stmt``. The owning node creates one input port per name."""
    seen: dict[str, None] = {}  # insertion-ordered set
    if isinstance(stmt, SelectStmt):
        sources: list[Value] = [cond.value for cond in stmt.where]
    else:
        sources = list(stmt.values)
    for src in sources:
        if isinstance(src, Placeholder):
            seen.setdefault(src.name, None)
    return list(seen)


# --------------------------------------------------------------- evaluator


def _resolve(value: Value, params: dict[str, Any]) -> Any:
    if isinstance(value, Placeholder):
        if value.name not in params:
            raise KeyError(
                f"Query placeholder ':{value.name}' has no bound value"
            )
        return params[value.name]
    return value


_OPS = {
    "=":  lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<":  lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">":  lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def execute(
    stmt: Statement,
    *,
    table_rows: list[dict[str, Any]],
    params: dict[str, Any],
) -> Any:
    """Evaluate ``stmt`` against ``table_rows`` (a *mutable* list) using
    ``params`` to bind placeholders.

    * ``SELECT`` returns a new list of matching rows (shallow copies).
    * ``INSERT`` appends a row to ``table_rows`` and returns the inserted
      row.

    The caller is responsible for fetching the correct ``table_rows`` list
    out of the ``DatabaseState`` based on ``stmt.table``.
    """
    if isinstance(stmt, SelectStmt):
        matches: list[dict[str, Any]] = []
        for row in table_rows:
            if all(
                _OPS[cond.op](row.get(cond.column), _resolve(cond.value, params))
                for cond in stmt.where
            ):
                matches.append(dict(row))
        return matches
    if isinstance(stmt, InsertStmt):
        row = {
            column: _resolve(value, params)
            for column, value in zip(stmt.columns, stmt.values)
        }
        table_rows.append(dict(row))
        return dict(row)
    raise ValueError(f"Unsupported statement type: {type(stmt).__name__}")
