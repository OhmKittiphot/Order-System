"""In-memory DynamoDB used by unit tests and the local dev server.

It implements the same interface as ``order_system.repositories.gateway``
and *evaluates* the subset of DynamoDB expression syntax the application
uses, so conditional writes, transactions and GSI queries behave like the
real service:

* Condition / key-condition / filter expressions: ``AND``, ``OR``, ``NOT``,
  parentheses, ``= <> < <= > >=``, ``IN (...)``, ``BETWEEN``,
  ``attribute_exists``, ``attribute_not_exists``, ``begins_with``, ``size``.
* Update expressions: ``SET`` (with ``+``/``-``, ``if_not_exists``,
  ``list_append``), ``REMOVE``, ``ADD``.
* Transactions are all-or-nothing, report per-item cancellation reasons and
  reject two operations on the same item (like DynamoDB).
* GSIs are sparse: items without the index key attributes are not indexed.

It is NOT a complete DynamoDB emulator; it exists so business logic can be
tested deterministically without network access or third-party packages.
"""

from __future__ import annotations

import copy
import re
import threading
from dataclasses import dataclass, field
from typing import Any

from order_system.utils.errors import ConditionFailedError, TransactionCanceledError

_MISSING = object()


@dataclass
class IndexDef:
    partition_key: str
    sort_key: str | None = None


@dataclass
class TableDef:
    name: str
    partition_key: str
    sort_key: str | None = None
    indexes: dict[str, IndexDef] = field(default_factory=dict)

    def key_of(self, item: dict[str, Any]) -> tuple[Any, ...]:
        if self.sort_key:
            return (item[self.partition_key], item[self.sort_key])
        return (item[self.partition_key],)

    def key_attrs(self) -> list[str]:
        return [self.partition_key] + ([self.sort_key] if self.sort_key else [])


# ---------------------------------------------------------------------------
# Expression tokenizer / parser / evaluator
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"\s*(?:(?P<op><>|<=|>=|=|<|>|\(|\)|,|\+|-)|(?P<name>#[A-Za-z0-9_]+)|(?P<value>:[A-Za-z0-9_]+)|(?P<word>[A-Za-z_][A-Za-z0-9_.]*))"
)


def _tokenize(expr: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    expr = expr.strip()
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m or m.end() == pos:
            raise ValueError(f"Cannot tokenize expression near: {expr[pos : pos + 20]!r}")
        pos = m.end()
        kind = m.lastgroup
        assert kind is not None
        tokens.append((kind, m.group(kind)))
    return tokens


class _Parser:
    def __init__(self, expr: str, names: dict[str, str], values: dict[str, Any]) -> None:
        self.tokens = _tokenize(expr)
        self.i = 0
        self.names = names
        self.values = values
        self.used_names: set[str] = set()
        self.used_values: set[str] = set()

    # -- token helpers -----------------------------------------------------
    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def peek_word(self) -> str | None:
        tok = self.peek()
        return tok[1].upper() if tok and tok[0] == "word" else None

    def take(self, value: str | None = None) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if value is not None and tok[1].upper() != value.upper():
            raise ValueError(f"Expected {value!r} but found {tok[1]!r}")
        self.i += 1
        return tok

    def done(self) -> bool:
        return self.i >= len(self.tokens)

    # -- operands ------------------------------------------------------------
    def path(self) -> str:
        kind, text = self.take()
        if kind == "name":
            if text not in self.names:
                raise ValueError(f"Undefined expression attribute name {text}")
            self.used_names.add(text)
            return self.names[text]
        if kind == "word":
            return text
        raise ValueError(f"Expected attribute path, found {text!r}")

    def operand(self) -> Any:
        """Returns a callable item -> value."""
        kind, text = self.peek() or ("", "")
        if kind == "value":
            self.take()
            if text not in self.values:
                raise ValueError(f"Undefined expression attribute value {text}")
            self.used_values.add(text)
            v = self.values[text]
            return lambda item, v=v: v
        if kind == "word" and text.lower() == "size":
            self.take()
            self.take("(")
            p = self.path()
            self.take(")")

            def size(item: dict[str, Any], p: str = p) -> Any:
                v = item.get(p, _MISSING)
                return _MISSING if v is _MISSING else len(v)

            return size
        if kind == "word" and text.lower() == "if_not_exists":
            self.take()
            self.take("(")
            p = self.path()
            self.take(",")
            default = self.operand()
            self.take(")")
            return lambda item, p=p, d=default: item[p] if p in item else d(item)
        if kind == "word" and text.lower() == "list_append":
            self.take()
            self.take("(")
            a = self.operand()
            self.take(",")
            b = self.operand()
            self.take(")")
            return lambda item, a=a, b=b: list(a(item)) + list(b(item))
        p = self.path()
        return lambda item, p=p: item.get(p, _MISSING)

    # -- conditions ----------------------------------------------------------
    def condition(self) -> Any:
        left = self._and()
        while self.peek_word() == "OR":
            self.take()
            right = self._and()
            left = (lambda a, b: lambda item: a(item) or b(item))(left, right)
        return left

    def _and(self) -> Any:
        left = self._not()
        while self.peek_word() == "AND":
            self.take()
            right = self._not()
            left = (lambda a, b: lambda item: a(item) and b(item))(left, right)
        return left

    def _not(self) -> Any:
        if self.peek_word() == "NOT":
            self.take()
            inner = self._not()
            return lambda item: not inner(item)
        return self._primary()

    def _primary(self) -> Any:
        tok = self.peek()
        if tok and tok[1] == "(":
            self.take()
            inner = self.condition()
            self.take(")")
            return inner
        word = self.peek_word()
        if word in {"ATTRIBUTE_EXISTS", "ATTRIBUTE_NOT_EXISTS"}:
            self.take()
            self.take("(")
            p = self.path()
            self.take(")")
            if word == "ATTRIBUTE_EXISTS":
                return lambda item, p=p: p in item
            return lambda item, p=p: p not in item
        if word == "BEGINS_WITH":
            self.take()
            self.take("(")
            a = self.operand()
            self.take(",")
            b = self.operand()
            self.take(")")

            def begins(item: dict[str, Any]) -> bool:
                x, y = a(item), b(item)
                return isinstance(x, str) and isinstance(y, str) and x.startswith(y)

            return begins
        left = self.operand()
        word = self.peek_word()
        if word == "IN":
            self.take()
            self.take("(")
            options = [self.operand()]
            while self.peek() and self.peek()[1] == ",":  # type: ignore[index]
                self.take(",")
                options.append(self.operand())
            self.take(")")
            return lambda item: (v := left(item)) is not _MISSING and any(v == o(item) for o in options)
        if word == "BETWEEN":
            self.take()
            lo = self.operand()
            self.take("AND")
            hi = self.operand()
            return lambda item: _cmp(left(item), ">=", lo(item)) and _cmp(left(item), "<=", hi(item))
        op = self.take()[1]
        if op not in {"=", "<>", "<", "<=", ">", ">="}:
            raise ValueError(f"Unsupported operator {op!r}")
        right = self.operand()
        return lambda item: _cmp(left(item), op, right(item))

    # -- update expressions -------------------------------------------------
    def update(self) -> list[tuple[str, str, Any]]:
        actions: list[tuple[str, str, Any]] = []
        while not self.done():
            clause = self.take()[1].upper()
            if clause not in {"SET", "REMOVE", "ADD"}:
                raise ValueError(f"Unsupported update clause {clause}")
            while True:
                if clause == "SET":
                    p = self.path()
                    self.take("=")
                    value = self.operand()
                    tok = self.peek()
                    if tok and tok[1] in {"+", "-"}:
                        sign = self.take()[1]
                        rhs = self.operand()
                        value = (lambda a, b, s: lambda item: _arith(a(item), s, b(item)))(value, rhs, sign)
                    actions.append(("SET", p, value))
                elif clause == "REMOVE":
                    actions.append(("REMOVE", self.path(), None))
                else:
                    p = self.path()
                    actions.append(("ADD", p, self.operand()))
                tok = self.peek()
                if tok and tok[1] == ",":
                    self.take()
                    continue
                break
        return actions

    def check_all_used(self) -> None:
        unused_names = set(self.names) - self.used_names
        unused_values = set(self.values) - self.used_values
        if unused_names or unused_values:
            # DynamoDB rejects unused placeholders; catching it here finds bugs early.
            raise ValueError(f"Unused expression attributes: {sorted(unused_names | unused_values)}")


def _cmp(a: Any, op: str, b: Any) -> bool:
    if a is _MISSING or b is _MISSING:
        return op == "<>"
    if op == "=":
        return bool(a == b)
    if op == "<>":
        return bool(a != b)
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return False
    try:
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    except TypeError:
        return False


def _arith(a: Any, sign: str, b: Any) -> Any:
    if a is _MISSING or b is _MISSING:
        raise ValueError("The provided expression refers to an attribute that does not exist in the item")
    if not isinstance(a, int) or not isinstance(b, int):
        raise ValueError("An operand in the update expression has an incorrect data type")
    return a + b if sign == "+" else a - b


def _compile_condition(expr: str, names: dict[str, str], values: dict[str, Any], parsers: list[_Parser]) -> Any:
    parser = _Parser(expr, names, values)
    fn = parser.condition()
    if not parser.done():
        raise ValueError(f"Unexpected trailing tokens in {expr!r}")
    parsers.append(parser)
    return fn


# ---------------------------------------------------------------------------
# The gateway
# ---------------------------------------------------------------------------


class MemoryDynamoGateway:
    def __init__(self, tables: list[TableDef]) -> None:
        self.tables = {t.name: t for t in tables}
        self.data: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = {t.name: {} for t in tables}
        self.lock = threading.RLock()
        self.write_count = 0

    # -- helpers -------------------------------------------------------------
    def _table(self, name: str) -> TableDef:
        if name not in self.tables:
            raise KeyError(f"ResourceNotFoundException: table {name} does not exist")
        return self.tables[name]

    def _key(self, table: TableDef, key: dict[str, Any]) -> tuple[Any, ...]:
        if set(key) != set(table.key_attrs()):
            raise ValueError(f"Key {key} does not match schema {table.key_attrs()} of {table.name}")
        return table.key_of(key)

    @staticmethod
    def _validate_item(item: dict[str, Any]) -> None:
        def check(v: Any) -> None:
            if isinstance(v, float):
                raise ValueError("Floats are not supported; store integers (minor units)")
            if isinstance(v, dict):
                for x in v.values():
                    check(x)
            if isinstance(v, list):
                for x in v:
                    check(x)

        for v in item.values():
            check(v)

    def _check(self, expr: str | None, item: dict[str, Any] | None, names: dict | None, values: dict | None) -> bool:
        if not expr:
            return True
        parsers: list[_Parser] = []
        fn = _compile_condition(expr, names or {}, values or {}, parsers)
        return bool(fn(item or {}))

    def _apply_update(
        self,
        table: TableDef,
        existing: dict[str, Any] | None,
        key: dict[str, Any],
        update: str,
        names: dict[str, str],
        values: dict[str, Any],
        condition_parser: _Parser | None,
    ) -> dict[str, Any]:
        parser = _Parser(update, names, values)
        actions = parser.update()
        if condition_parser is not None:
            parser.used_names |= condition_parser.used_names
            parser.used_values |= condition_parser.used_values
        parser.check_all_used()
        base = copy.deepcopy(existing) if existing else copy.deepcopy(key)
        computed = []
        for kind, path, value in actions:
            if path in table.key_attrs():
                raise ValueError("Cannot update attribute that is part of the key")
            computed.append((kind, path, value(base) if value is not None else None))
        new = copy.deepcopy(base)
        for kind, path, value in computed:
            if kind == "SET":
                if value is _MISSING:
                    raise ValueError(f"SET {path} refers to a missing attribute")
                new[path] = copy.deepcopy(value)
            elif kind == "REMOVE":
                new.pop(path, None)
            elif kind == "ADD":
                current = new.get(path, 0)
                if not isinstance(current, int) or not isinstance(value, int):
                    raise ValueError("ADD only supports numbers in this emulator")
                new[path] = current + value
        self._validate_item(new)
        return new

    def _condition_and_parser(
        self, expr: str | None, names: dict | None, values: dict | None
    ) -> tuple[Any, _Parser | None]:
        if not expr:
            return (lambda item: True), None
        parsers: list[_Parser] = []
        fn = _compile_condition(expr, names or {}, values or {}, parsers)
        return fn, parsers[0]

    # -- interface -------------------------------------------------------------
    def get(self, table: str, key: dict[str, Any], *, consistent: bool = True) -> dict[str, Any] | None:
        with self.lock:
            t = self._table(table)
            item = self.data[table].get(self._key(t, key))
            return copy.deepcopy(item)

    def put(self, table, item, *, condition=None, names=None, values=None) -> None:  # type: ignore[no-untyped-def]
        with self.lock:
            t = self._table(table)
            self._validate_item(item)
            k = t.key_of(item)
            fn, parser = self._condition_and_parser(condition, names, values)
            if parser:
                parser.check_all_used()
            if not fn(self.data[table].get(k) or {}):
                raise ConditionFailedError(f"Condition failed on {table} {k}")
            self.data[table][k] = copy.deepcopy(item)
            self.write_count += 1

    def update(self, table, key, update, *, condition=None, names=None, values=None):  # type: ignore[no-untyped-def]
        with self.lock:
            t = self._table(table)
            k = self._key(t, key)
            existing = self.data[table].get(k)
            fn, parser = self._condition_and_parser(condition, names, values)
            if not fn(existing or {}):
                raise ConditionFailedError(f"Condition failed on {table} {k}")
            new = self._apply_update(t, existing, key, update, names or {}, values or {}, parser)
            self.data[table][k] = new
            self.write_count += 1
            return copy.deepcopy(new)

    def delete(self, table, key, *, condition=None, names=None, values=None) -> None:  # type: ignore[no-untyped-def]
        with self.lock:
            t = self._table(table)
            k = self._key(t, key)
            fn, _ = self._condition_and_parser(condition, names, values)
            if not fn(self.data[table].get(k) or {}):
                raise ConditionFailedError(f"Condition failed on {table} {k}")
            self.data[table].pop(k, None)

    def _index_items(self, t: TableDef, index: str | None) -> tuple[list[dict[str, Any]], str, str | None]:
        if index is None:
            pk, sk = t.partition_key, t.sort_key
        else:
            if index not in t.indexes:
                raise ValueError(f"Index {index} not defined on {t.name}")
            pk, sk = t.indexes[index].partition_key, t.indexes[index].sort_key
        items = [i for i in self.data[t.name].values() if pk in i and (sk is None or sk in i)]
        return items, pk, sk

    def query(
        self,
        table,
        *,
        key_condition,
        names=None,
        values=None,
        index=None,
        filter_expression=None,  # type: ignore[no-untyped-def]
        limit=None,
        start_key=None,
        forward=True,
        consistent=False,
    ):
        with self.lock:
            t = self._table(table)
            items, pk, sk = self._index_items(t, index)
            parsers: list[_Parser] = []
            key_fn = _compile_condition(key_condition, names or {}, values or {}, parsers)
            filter_fn = (
                _compile_condition(filter_expression, names or {}, values or {}, parsers)
                if filter_expression
                else (lambda item: True)
            )
            merged = _Parser("", names or {}, values or {})
            for p in parsers:
                merged.used_names |= p.used_names
                merged.used_values |= p.used_values
            merged.check_all_used()
            matched = [i for i in items if key_fn(i)]
            if index is not None and pk not in _key_condition_attrs(key_condition, names or {}):
                raise ValueError("Query key condition must include the partition key")
            matched.sort(key=lambda i: (i.get(sk, "") if sk else "", t.key_of(i)), reverse=not forward)
            return self._page(t, matched, filter_fn, limit, start_key, index, pk, sk)

    def _page(self, t, matched, filter_fn, limit, start_key, index, pk, sk):  # type: ignore[no-untyped-def]
        start = 0
        if start_key:
            target = t.key_of(start_key)
            for pos, item in enumerate(matched):
                if t.key_of(item) == target:
                    start = pos + 1
                    break
        window = matched[start:]
        evaluated = window[:limit] if limit else window
        result = [copy.deepcopy(i) for i in evaluated if filter_fn(i)]
        last = None
        if limit and len(window) > limit:
            tail = evaluated[-1]
            last = {a: tail[a] for a in t.key_attrs()}
            if index:
                last[pk] = tail[pk]
                if sk:
                    last[sk] = tail[sk]
        return result, last

    def count(self, table, *, key_condition, names=None, values=None, index=None) -> int:  # type: ignore[no-untyped-def]
        items, _ = self.query(table, key_condition=key_condition, names=names, values=values, index=index)
        return len(items)

    def scan(self, table, *, limit=None, start_key=None):  # type: ignore[no-untyped-def]
        with self.lock:
            t = self._table(table)
            items = sorted(self.data[table].values(), key=lambda i: t.key_of(i))
            return self._page(t, items, lambda i: True, limit, start_key, None, t.partition_key, t.sort_key)

    def batch_get(self, table: str, keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self.lock:
            if len(keys) > 100:
                raise ValueError("Too many keys")
            out = []
            for key in keys:
                item = self.get(table, key)
                if item is not None:
                    out.append(item)
            return out

    def transact_write(self, operations: list[dict[str, Any]]) -> None:
        with self.lock:
            if len(operations) > 100:
                raise ValueError("Transactions support at most 100 items")
            seen: set[tuple[str, tuple[Any, ...]]] = set()
            plans: list[tuple[str, str, tuple[Any, ...], dict[str, Any] | None]] = []
            reasons: list[str | None] = []
            for op in operations:
                ((kind, body),) = op.items()
                table = body["TableName"]
                t = self._table(table)
                if kind == "Put":
                    self._validate_item(body["Item"])
                    k = t.key_of(body["Item"])
                else:
                    k = self._key(t, body["Key"])
                if (table, k) in seen:
                    raise ValueError("Transaction request cannot include multiple operations on one item")
                seen.add((table, k))
                existing = self.data[table].get(k)
                names = body.get("ExpressionAttributeNames") or {}
                values = body.get("ExpressionAttributeValues") or {}
                fn, parser = self._condition_and_parser(body.get("ConditionExpression"), names, values)
                ok = fn(existing or {})
                new_item: dict[str, Any] | None = None
                if kind == "Put":
                    if parser:
                        parser.check_all_used()
                    new_item = copy.deepcopy(body["Item"])
                elif kind == "Update":
                    new_item = self._apply_update(
                        t, existing, body["Key"], body["UpdateExpression"], names, values, parser
                    )
                elif kind == "Delete":
                    new_item = None
                elif kind == "ConditionCheck":
                    if parser:
                        parser.check_all_used()
                else:
                    raise ValueError(f"Unsupported transaction operation {kind}")
                reasons.append(None if ok else "ConditionalCheckFailed")
                plans.append((kind, table, k, new_item))
            if any(r is not None for r in reasons):
                raise TransactionCanceledError([r or "None" for r in reasons])
            for kind, table, k, new_item in plans:
                if kind in {"Put", "Update"}:
                    assert new_item is not None
                    self.data[table][k] = new_item
                elif kind == "Delete":
                    self.data[table].pop(k, None)
            self.write_count += 1


def _key_condition_attrs(expr: str, names: dict[str, str]) -> set[str]:
    attrs = set()
    for kind, text in _tokenize(expr):
        if kind == "name":
            attrs.add(names.get(text, text))
        elif kind == "word" and text.upper() not in {"AND", "BEGINS_WITH", "BETWEEN"}:
            attrs.add(text)
    return attrs
