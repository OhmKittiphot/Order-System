"""Request validation. Every API handler validates input here before any
business logic or database access runs. Unknown fields are rejected so a
client cannot smuggle in ``price``, ``total``, ``role`` or ``status``."""

from __future__ import annotations

import re
from typing import Any, TypeGuard

from ..config.settings import Settings
from ..utils.common import require_id
from ..utils.errors import ValidationError

TEST_BEHAVIORS = ("PAYMENT_DECLINE", "PAYMENT_TRANSIENT_ONCE")
QUEUE_NAMES = ("stock", "payment", "notify")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")
_IDEM_RE = re.compile(r"^[A-Za-z0-9_\-]{8,128}$")
_URL_RE = re.compile(r"^https://[^\s<>\"']{3,490}$")


def _is_int(v: Any) -> TypeGuard[int]:
    return isinstance(v, int) and not isinstance(v, bool)


def _reject_unknown(body: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise ValidationError("Unknown fields in request", details={"fields": unknown})


def _string(body: dict[str, Any], field: str, *, required: bool, min_len: int = 1, max_len: int = 200) -> str | None:
    value = body.get(field)
    if value is None:
        if required:
            raise ValidationError(f"{field} is required", details={"field": field})
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string", details={"field": field})
    value = value.strip()
    if not (min_len <= len(value) <= max_len):
        raise ValidationError(f"{field} must be {min_len}-{max_len} characters", details={"field": field})
    return value


def _int_field(body: dict[str, Any], field: str, *, required: bool, minimum: int, maximum: int) -> int | None:
    value = body.get(field)
    if value is None:
        if required:
            raise ValidationError(f"{field} is required", details={"field": field})
        return None
    if not _is_int(value):
        raise ValidationError(f"{field} must be an integer", details={"field": field})
    if not (minimum <= value <= maximum):
        raise ValidationError(f"{field} must be between {minimum} and {maximum}", details={"field": field})
    return int(value)


# --- orders -----------------------------------------------------------------


def validate_idempotency_key(raw: str | None) -> str:
    if not raw:
        raise ValidationError("Idempotency-Key header is required", code="IDEMPOTENCY_KEY_REQUIRED")
    if not _IDEM_RE.match(raw):
        raise ValidationError("Idempotency-Key must be 8-128 characters [A-Za-z0-9_-]")
    return raw


def validate_create_order(body: dict[str, Any], settings: Settings) -> list[tuple[str, int]]:
    """Returns merged ``(productId, quantity)`` lines in request order.

    Prices and totals are deliberately not accepted: the server reads them
    from the Products table.
    """
    _reject_unknown(body, {"items"})
    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise ValidationError("items must be a non-empty array")
    if len(items) > settings.max_order_items:
        raise ValidationError(f"An order can contain at most {settings.max_order_items} lines")
    merged: dict[str, int] = {}
    for index, line in enumerate(items):
        if not isinstance(line, dict):
            raise ValidationError("Each item must be an object", details={"index": index})
        _reject_unknown(line, {"productId", "quantity"})
        product_id = require_id(line.get("productId"), f"items[{index}].productId")
        raw_qty = line.get("quantity")
        if not _is_int(raw_qty) or not (1 <= raw_qty <= settings.max_item_quantity):
            raise ValidationError(
                f"items[{index}].quantity must be an integer between 1 and {settings.max_item_quantity}",
                details={"index": index},
            )
        merged[product_id] = merged.get(product_id, 0) + raw_qty
        if merged[product_id] > settings.max_item_quantity:
            raise ValidationError(f"Total quantity for {product_id} exceeds {settings.max_item_quantity}")
    return list(merged.items())


# --- products -----------------------------------------------------------------


def _test_behavior(body: dict[str, Any]) -> tuple[bool, str | None]:
    if "testBehavior" not in body:
        return False, None
    value = body["testBehavior"]
    if value in (None, ""):
        return True, None
    if value not in TEST_BEHAVIORS:
        raise ValidationError(f"testBehavior must be one of {', '.join(TEST_BEHAVIORS)} or null")
    return True, value


def _image_url(body: dict[str, Any]) -> tuple[bool, str | None]:
    if "imageUrl" not in body:
        return False, None
    value = body["imageUrl"]
    if value in (None, ""):
        return True, None
    if not isinstance(value, str) or not _URL_RE.match(value):
        raise ValidationError("imageUrl must be an https URL")
    return True, value


def validate_product_create(body: dict[str, Any]) -> dict[str, Any]:
    _reject_unknown(
        body, {"name", "description", "priceMinor", "imageUrl", "category", "active", "initialStock", "testBehavior"}
    )
    out: dict[str, Any] = {
        "name": _string(body, "name", required=True, max_len=120),
        "description": _string(body, "description", required=False, min_len=0, max_len=1000) or "",
        "priceMinor": _int_field(body, "priceMinor", required=True, minimum=1, maximum=100_000_000),
        "category": _string(body, "category", required=False, max_len=60) or "General",
        "initialStock": _int_field(body, "initialStock", required=False, minimum=0, maximum=1_000_000) or 0,
    }
    active = body.get("active", True)
    if not isinstance(active, bool):
        raise ValidationError("active must be a boolean")
    out["active"] = active
    _, out["imageUrl"] = _image_url(body)
    _, out["testBehavior"] = _test_behavior(body)
    return out


def validate_product_update(body: dict[str, Any]) -> dict[str, Any]:
    _reject_unknown(body, {"name", "description", "priceMinor", "imageUrl", "category", "active", "testBehavior"})
    changes: dict[str, Any] = {}
    if "name" in body:
        changes["name"] = _string(body, "name", required=True, max_len=120)
    if "description" in body:
        changes["description"] = _string(body, "description", required=True, min_len=0, max_len=1000)
    if "priceMinor" in body:
        changes["priceMinor"] = _int_field(body, "priceMinor", required=True, minimum=1, maximum=100_000_000)
    if "category" in body:
        changes["category"] = _string(body, "category", required=True, max_len=60)
    if "active" in body:
        if not isinstance(body["active"], bool):
            raise ValidationError("active must be a boolean")
        changes["active"] = body["active"]
    present, url = _image_url(body)
    if present:
        changes["imageUrl"] = url
    present, behavior = _test_behavior(body)
    if present:
        changes["testBehavior"] = behavior
    if not changes:
        raise ValidationError("No editable fields supplied")
    return changes


def validate_stock_change(body: dict[str, Any]) -> tuple[str, int, str]:
    """``{"mode": "set"|"adjust", "quantity": n, "reason": "..."}``"""
    _reject_unknown(body, {"mode", "quantity", "reason"})
    mode = body.get("mode", "set")
    if mode not in ("set", "adjust"):
        raise ValidationError("mode must be 'set' or 'adjust'")
    if mode == "set":
        qty = _int_field(body, "quantity", required=True, minimum=0, maximum=1_000_000)
    else:
        qty = _int_field(body, "quantity", required=True, minimum=-1_000_000, maximum=1_000_000)
        if qty == 0:
            raise ValidationError("adjust quantity must not be zero")
    reason = _string(body, "reason", required=False, min_len=0, max_len=200) or ""
    assert qty is not None
    return mode, qty, reason


# --- auth ---------------------------------------------------------------------


def validate_email(value: Any) -> str:
    if not isinstance(value, str) or not _EMAIL_RE.match(value.strip()):
        raise ValidationError("A valid email is required", details={"field": "email"})
    return value.strip().lower()


def validate_password(value: Any) -> str:
    if not isinstance(value, str) or not (8 <= len(value) <= 128):
        raise ValidationError("Password must be 8-128 characters", details={"field": "password"})
    if not (any(c.isdigit() for c in value) and any(c.islower() for c in value) and any(c.isupper() for c in value)):
        raise ValidationError(
            "Password does not meet the policy (min 8 chars, upper, lower, number)",
            code="WEAK_PASSWORD",
            details={"field": "password"},
        )
    return value


def validate_register(body: dict[str, Any]) -> tuple[str, str, str]:
    _reject_unknown(body, {"email", "password", "displayName"})
    email = validate_email(body.get("email"))
    password = validate_password(body.get("password"))
    name = _string(body, "displayName", required=True, max_len=80)
    assert name is not None
    return email, password, name


def validate_login(body: dict[str, Any]) -> tuple[str, str]:
    _reject_unknown(body, {"email", "password"})
    email = validate_email(body.get("email"))
    password = body.get("password")
    if not isinstance(password, str) or not password or len(password) > 128:
        raise ValidationError("password is required", details={"field": "password"})
    return email, password


def validate_queue_name(value: str) -> str:
    if value not in QUEUE_NAMES:
        raise ValidationError(f"queue must be one of {', '.join(QUEUE_NAMES)}")
    return value


def validate_status_filter(value: str | None) -> str | None:
    from ..models.order_states import OrderStatus

    if not value:
        return None
    if value not in OrderStatus.ALL:
        raise ValidationError(f"status must be one of {', '.join(OrderStatus.ALL)}")
    return value
