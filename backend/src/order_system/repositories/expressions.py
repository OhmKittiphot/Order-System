"""Builds DynamoDB update/condition expressions with safe placeholders.

Using placeholders for every attribute name and value avoids reserved-word
problems (``status``, ``name``) and makes it impossible for user input to
alter an expression.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UpdateSpec:
    update: str
    condition: str | None
    names: dict[str, str] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)

    def as_transact(self, table: str, key: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "TableName": table,
            "Key": key,
            "UpdateExpression": self.update,
            "ExpressionAttributeNames": self.names,
        }
        if self.values:
            body["ExpressionAttributeValues"] = self.values
        if self.condition:
            body["ConditionExpression"] = self.condition
        return {"Update": body}


def build_update(
    *,
    set_fields: dict[str, Any] | None = None,
    increments: dict[str, int] | None = None,
    remove: list[str] | tuple[str, ...] = (),
    append: dict[str, list[Any]] | None = None,
    expect_equal: dict[str, Any] | None = None,
    expect_in: dict[str, list[Any]] | None = None,
    expect_at_least: dict[str, int] | None = None,
    must_exist: str | None = None,
    expect_absent: list[str] | tuple[str, ...] = (),
    extra_condition: str | None = None,
    extra_names: dict[str, str] | None = None,
    extra_values: dict[str, Any] | None = None,
) -> UpdateSpec:
    names: dict[str, str] = dict(extra_names or {})
    values: dict[str, Any] = dict(extra_values or {})
    sets: list[str] = []
    counter = 0

    def name(attr: str) -> str:
        for placeholder, existing in names.items():
            if existing == attr:
                return placeholder
        nonlocal counter
        counter += 1
        placeholder = f"#n{counter}"
        names[placeholder] = attr
        return placeholder

    def value(v: Any) -> str:
        nonlocal counter
        counter += 1
        placeholder = f":v{counter}"
        values[placeholder] = v
        return placeholder

    for attr, v in (set_fields or {}).items():
        sets.append(f"{name(attr)} = {value(v)}")
    for attr, delta in (increments or {}).items():
        n = name(attr)
        sets.append(f"{n} = {n} + {value(delta)}")
    for attr, items in (append or {}).items():
        n = name(attr)
        sets.append(f"{n} = list_append(if_not_exists({n}, {value([])}), {value(items)})")

    parts = []
    if sets:
        parts.append("SET " + ", ".join(sets))
    if remove:
        parts.append("REMOVE " + ", ".join(name(a) for a in remove))

    conditions: list[str] = []
    if must_exist:
        conditions.append(f"attribute_exists({name(must_exist)})")
    for attr, v in (expect_equal or {}).items():
        conditions.append(f"{name(attr)} = {value(v)}")
    for attr, options in (expect_in or {}).items():
        conditions.append(f"{name(attr)} IN ({', '.join(value(o) for o in options)})")
    for attr, minimum in (expect_at_least or {}).items():
        conditions.append(f"{name(attr)} >= {value(minimum)}")
    for attr in expect_absent:
        conditions.append(f"attribute_not_exists({name(attr)})")
    if extra_condition:
        conditions.append(f"({extra_condition})")

    return UpdateSpec(
        update=" ".join(parts),
        condition=" AND ".join(conditions) if conditions else None,
        names=names,
        values=values,
    )
