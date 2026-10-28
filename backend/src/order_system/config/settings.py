"""Runtime configuration read from Lambda environment variables.

Every value has a safe default so unit tests and the local dev server can
construct settings without a full AWS environment. The only secret is
JWT_SECRET (Auth Lambda + Authorizer); AWS credentials come from the Lambda
execution role.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # misconfiguration should fail loudly at cold start
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


@dataclass(frozen=True)
class QueueConfig:
    """URLs/ARNs of one service queue and its DLQ (used by admin operations)."""

    name: str
    queue_url: str = ""
    queue_arn: str = ""
    dlq_url: str = ""
    dlq_arn: str = ""


@dataclass(frozen=True)
class Settings:
    service_name: str = "order-system"
    environment: str = "dev"
    region: str = "us-east-1"

    orders_table: str = "orders"
    products_table: str = "products"
    inventory_table: str = "inventory"
    payments_table: str = "payments"
    notifications_table: str = "notifications"
    users_table: str = "users"
    idempotency_table: str = "idempotency"

    order_events_topic_arn: str = ""
    customer_email_topic_arn: str = ""
    customer_email_enabled: bool = False

    # HS256 key shared by the Auth Lambda and the Lambda Authorizer only.
    jwt_secret: str = ""
    access_token_ttl_seconds: int = 3600
    refresh_token_ttl_seconds: int = 86400

    currency: str = "THB"
    low_stock_threshold: int = 5
    max_order_items: int = 20
    max_item_quantity: int = 99
    idempotency_ttl_hours: int = 24

    payment_simulation_mode: str = "deterministic"  # deterministic | random
    payment_failure_rate: float = 0.0
    enable_test_scenarios: bool = True

    stuck_order_seconds: int = 120
    retry_cooldown_seconds: int = 30
    max_retries: int = 5
    outbox_min_age_seconds: int = 30

    # Worker-specific: DLQ that permanent (non-retryable) failures are parked in.
    own_dlq_url: str = ""
    queues: dict[str, QueueConfig] = field(default_factory=dict)
    alarm_name_prefix: str = ""

    @property
    def jwt_issuer(self) -> str:
        return f"{self.service_name}-{self.environment}"

    @property
    def is_payment_random(self) -> bool:
        return self.payment_simulation_mode == "random"


def _parse_queues(raw: str) -> dict[str, QueueConfig]:
    if not raw:
        return {}
    data = json.loads(raw)
    queues: dict[str, QueueConfig] = {}
    for name, cfg in data.items():
        queues[name] = QueueConfig(
            name=name,
            queue_url=cfg.get("queueUrl", ""),
            queue_arn=cfg.get("queueArn", ""),
            dlq_url=cfg.get("dlqUrl", ""),
            dlq_arn=cfg.get("dlqArn", ""),
        )
    return queues


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        service_name=env("SERVICE_NAME", "order-system"),
        environment=env("ENVIRONMENT", "dev"),
        region=env("AWS_REGION", env("AWS_DEFAULT_REGION", "us-east-1")),
        orders_table=env("ORDERS_TABLE", "orders"),
        products_table=env("PRODUCTS_TABLE", "products"),
        inventory_table=env("INVENTORY_TABLE", "inventory"),
        payments_table=env("PAYMENTS_TABLE", "payments"),
        notifications_table=env("NOTIFICATIONS_TABLE", "notifications"),
        users_table=env("USERS_TABLE", "users"),
        idempotency_table=env("IDEMPOTENCY_TABLE", "idempotency"),
        order_events_topic_arn=env("ORDER_EVENTS_TOPIC_ARN", ""),
        customer_email_topic_arn=env("CUSTOMER_EMAIL_TOPIC_ARN", ""),
        customer_email_enabled=_bool("CUSTOMER_EMAIL_ENABLED", False),
        jwt_secret=env("JWT_SECRET", ""),
        access_token_ttl_seconds=_int("ACCESS_TOKEN_TTL_SECONDS", 3600),
        refresh_token_ttl_seconds=_int("REFRESH_TOKEN_TTL_SECONDS", 86400),
        currency=env("CURRENCY", "THB"),
        low_stock_threshold=_int("LOW_STOCK_THRESHOLD", 5),
        max_order_items=_int("MAX_ORDER_ITEMS", 20),
        max_item_quantity=_int("MAX_ITEM_QUANTITY", 99),
        idempotency_ttl_hours=_int("IDEMPOTENCY_TTL_HOURS", 24),
        payment_simulation_mode=env("PAYMENT_SIMULATION_MODE", "deterministic"),
        payment_failure_rate=_float("PAYMENT_FAILURE_RATE", 0.0),
        enable_test_scenarios=_bool("ENABLE_TEST_SCENARIOS", True),
        stuck_order_seconds=_int("STUCK_ORDER_SECONDS", 120),
        retry_cooldown_seconds=_int("RETRY_COOLDOWN_SECONDS", 30),
        max_retries=_int("MAX_RETRIES", 5),
        outbox_min_age_seconds=_int("OUTBOX_MIN_AGE_SECONDS", 30),
        own_dlq_url=env("OWN_DLQ_URL", ""),
        queues=_parse_queues(env("QUEUES_JSON", "")),
        alarm_name_prefix=env("ALARM_NAME_PREFIX", ""),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
