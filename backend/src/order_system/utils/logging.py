"""Structured JSON logging with correlation and order ids.

Usage::

    log = get_logger("order-api")
    with log_context(correlationId=cid, orderId=oid):
        log.info("order created", totalMinor=1200)

Never pass tokens, passwords, card data or full request bodies to the logger.
Keys that look sensitive are redacted defensively.
"""

from __future__ import annotations

import contextvars
import json
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("log_context", default=None)


def _ctx() -> dict[str, Any]:
    return _context.get() or {}


_SENSITIVE = ("password", "token", "authorization", "secret", "card", "cvv")
_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}


def _redact(value: Any, key: str = "") -> Any:
    if any(s in key.lower() for s in _SENSITIVE):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


class JsonLogger:
    def __init__(self, service: str) -> None:
        self.service = service
        self.threshold = _LEVELS.get(os.environ.get("LOG_LEVEL", "INFO").upper(), 20)

    def _emit(self, level: str, message: str, fields: dict[str, Any]) -> None:
        if _LEVELS[level] < self.threshold:
            return
        record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": level,
            "service": self.service,
            "message": message,
        }
        record.update(_ctx())
        record.update(_redact(fields))
        sys.stdout.write(json.dumps(record, default=str) + "\n")

    def debug(self, message: str, **fields: Any) -> None:
        self._emit("DEBUG", message, fields)

    def info(self, message: str, **fields: Any) -> None:
        self._emit("INFO", message, fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._emit("WARNING", message, fields)

    def error(self, message: str, **fields: Any) -> None:
        self._emit("ERROR", message, fields)


def get_logger(service: str) -> JsonLogger:
    return JsonLogger(service)


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    current = dict(_ctx())
    current.update({k: v for k, v in fields.items() if v is not None})
    token = _context.set(current)
    started = time.monotonic()
    try:
        yield
    finally:
        _context.reset(token)
        _ = started


def bind(**fields: Any) -> None:
    """Add fields to the current context (e.g. orderId once it is known)."""
    current = dict(_ctx())
    current.update({k: v for k, v in fields.items() if v is not None})
    _context.set(current)


def current_correlation_id() -> str | None:
    return _ctx().get("correlationId")
