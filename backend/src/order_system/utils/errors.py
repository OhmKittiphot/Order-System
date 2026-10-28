"""Application error hierarchy.

HTTP handlers turn ``AppError`` subclasses into JSON error responses with the
right status code. SQS workers use ``TransientError`` (retry via SQS
redelivery) versus ``PermanentError`` (never retry; park in the DLQ).
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details


class ValidationError(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"


class TransientError(AppError):
    """A failure that may succeed if the message is processed again."""

    status_code = 503
    code = "TRANSIENT_ERROR"


class PermanentError(AppError):
    """A failure that will never succeed on retry (bad message, missing order)."""

    status_code = 422
    code = "PERMANENT_ERROR"


# --- data-layer errors (raised by the DynamoDB gateway and its fake) -------


class ConditionFailedError(Exception):
    """A conditional write's ConditionExpression evaluated to false."""


class TransactionCanceledError(Exception):
    """A TransactWriteItems call was cancelled.

    ``reasons`` has one entry per transaction item, in order; the entry is
    ``"ConditionalCheckFailed"`` for items whose condition failed, or
    ``None``/``"None"`` for items that were fine.
    """

    def __init__(self, reasons: list[str | None]) -> None:
        super().__init__(f"Transaction cancelled: {reasons}")
        self.reasons = reasons

    def failed_indexes(self) -> list[int]:
        return [i for i, r in enumerate(self.reasons) if r == "ConditionalCheckFailed"]

    @property
    def is_conflict(self) -> bool:
        """True when cancelled by a concurrent transaction (retryable)."""
        return any(r in {"TransactionConflict", "ThrottlingError"} for r in self.reasons)
