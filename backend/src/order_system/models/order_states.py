"""Order state machine constants and the allowed transitions.

Every write that changes ``status`` is a DynamoDB conditional update whose
condition encodes the *expected source state* from this table, so an
illegal, duplicate or late transition simply fails the condition instead of
overwriting newer data. See docs/order-workflow.md.
"""

from __future__ import annotations


class OrderStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    ALL = (PENDING, PROCESSING, CONFIRMED, FAILED, CANCELLED)
    TERMINAL = (CONFIRMED, CANCELLED)  # FAILED is terminal unless an admin retries


class InventoryStatus:
    PENDING = "PENDING"
    RESERVED = "RESERVED"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    COMMITTED = "COMMITTED"  # reservation consumed by a successful payment
    RELEASED = "RELEASED"  # reservation returned (payment failed / cancelled)


class PaymentStatus:
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"  # never attempted because inventory failed / order cancelled


class NotificationStatus:
    PENDING = "PENDING"
    SENT = "SENT"  # recorded in-app (and accepted by SNS when email is enabled)
    SKIPPED = "SKIPPED"


class FailureCategory:
    BUSINESS = "BUSINESS"  # e.g. out of stock; needs the cause fixed first
    PAYMENT_DECLINED = "PAYMENT_DECLINED"  # simulated decline; customer must re-order
    TRANSIENT = "TRANSIENT"  # infrastructure failure; safe to retry
    PERMANENT = "PERMANENT"  # invalid data; never retried automatically


# (from_status, to_status) -> trigger. Used by docs and tests; the
# repositories enforce the same rules with condition expressions.
TRANSITIONS: dict[tuple[str, str], str] = {
    (OrderStatus.PENDING, OrderStatus.PROCESSING): "stock reserved (InventoryReserved)",
    (OrderStatus.PENDING, OrderStatus.FAILED): "insufficient stock (OrderFailed)",
    (OrderStatus.PROCESSING, OrderStatus.CONFIRMED): "payment succeeded (OrderConfirmed)",
    (OrderStatus.PROCESSING, OrderStatus.FAILED): "payment declined, stock released (OrderFailed)",
    (OrderStatus.PENDING, OrderStatus.CANCELLED): "admin cancel",
    (OrderStatus.PROCESSING, OrderStatus.CANCELLED): "admin cancel, stock released",
    (OrderStatus.FAILED, OrderStatus.PENDING): "admin retry (retryable failure only)",
}


def is_allowed(from_status: str, to_status: str) -> bool:
    return (from_status, to_status) in TRANSITIONS
