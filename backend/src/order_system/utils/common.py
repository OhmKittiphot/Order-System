"""Small shared helpers: clock, ids, pagination tokens, backoff."""

from __future__ import annotations

import base64
import json
import random
import re
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from .errors import ValidationError

T = TypeVar("T")


# --- time -----------------------------------------------------------------

_clock_override: Callable[[], datetime] | None = None


def set_clock(fn: Callable[[], datetime] | None) -> None:
    """Tests use this to freeze or advance time."""
    global _clock_override
    _clock_override = fn


def utc_now() -> datetime:
    if _clock_override is not None:
        return _clock_override()
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def now_iso() -> str:
    return iso(utc_now())


def iso_seconds_ago(seconds: int) -> str:
    return iso(utc_now() - timedelta(seconds=seconds))


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def epoch_in(hours: int) -> int:
    return int((utc_now() + timedelta(hours=hours)).timestamp())


# --- ids ------------------------------------------------------------------


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{3,80}$")


def require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValidationError(f"{field} is not a valid identifier", details={"field": field})
    return value


# --- pagination -----------------------------------------------------------


def encode_token(key: dict[str, Any] | None) -> str | None:
    if not key:
        return None
    raw = json.dumps(key, separators=(",", ":"), sort_keys=True, default=int).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    if len(token) > 2048:
        raise ValidationError("nextToken is too long")
    try:
        padded = token + "=" * (-len(token) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValidationError("nextToken is invalid") from exc
    if not isinstance(data, dict) or not all(isinstance(v, (str, int)) for v in data.values()):
        raise ValidationError("nextToken is invalid")
    return data


def parse_limit(raw: Any, default: int = 20, maximum: int = 100) -> int:
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("limit must be an integer") from exc
    if value < 1 or value > maximum:
        raise ValidationError(f"limit must be between 1 and {maximum}")
    return value


# --- retry ----------------------------------------------------------------


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 1.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn`` with exponential backoff and full jitter.

    Only for short in-process retries of idempotent calls (e.g. SNS publish).
    Longer-term retries are SQS redelivery, not this function.
    """
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except retry_on as exc:  # noqa: PERF203 - deliberate retry loop
            last = exc
            if attempt == attempts - 1:
                break
            delay = min(max_delay, base_delay * (2**attempt))
            sleep(random.uniform(0, delay))  # noqa: S311 - jitter, not security
    assert last is not None
    raise last
