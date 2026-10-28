"""Dependency container. Lambda handlers call ``get_deps()``; tests and the
local dev server install in-memory implementations with ``set_deps()``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config.settings import Settings, get_settings
from ..repositories.aws_clients import (
    AlarmReader,
    EmailNotifier,
    EventPublisher,
    QueueAdmin,
)
from ..repositories.catalog import CatalogRepository
from ..repositories.gateway import DynamoGateway
from ..repositories.orders import OrdersRepository
from ..repositories.records import (
    NotificationsRepository,
    PaymentsRepository,
    UsersRepository,
)


@dataclass
class Deps:
    settings: Settings
    gw: DynamoGateway
    publisher: EventPublisher
    email: EmailNotifier | None
    queues: QueueAdmin | None
    alarms: AlarmReader | None

    @property
    def orders(self) -> OrdersRepository:
        return OrdersRepository(self.gw, self.settings)

    @property
    def catalog(self) -> CatalogRepository:
        return CatalogRepository(self.gw, self.settings)

    @property
    def payments(self) -> PaymentsRepository:
        return PaymentsRepository(self.gw, self.settings)

    @property
    def notifications(self) -> NotificationsRepository:
        return NotificationsRepository(self.gw, self.settings)

    @property
    def users(self) -> UsersRepository:
        return UsersRepository(self.gw, self.settings)


_deps: Deps | None = None


def _lazy(factory: Any) -> Any:
    try:
        return factory()
    except Exception:  # noqa: BLE001 - optional integrations may be unconfigured
        return None


def build_aws_deps(settings: Settings | None = None) -> Deps:
    from ..repositories.aws_clients import (
        CloudWatchAlarmReader,
        SnsEmailNotifier,
        SnsEventPublisher,
        SqsQueueAdmin,
    )
    from ..repositories.gateway import BotoDynamoGateway

    s = settings or get_settings()

    class _LazyPublisher:
        """Creates the SNS client on first use so read-only Lambdas without
        the topic ARN can still start."""

        _inner: SnsEventPublisher | None = None

        def publish(self, event):  # type: ignore[no-untyped-def]
            if self._inner is None:
                self._inner = SnsEventPublisher(s.order_events_topic_arn)
            return self._inner.publish(event)

    return Deps(
        settings=s,
        gw=BotoDynamoGateway(),
        publisher=_LazyPublisher(),
        email=_lazy(lambda: SnsEmailNotifier(s.customer_email_topic_arn))
        if s.customer_email_enabled and s.customer_email_topic_arn
        else None,
        queues=_lazy(SqsQueueAdmin),
        alarms=_lazy(CloudWatchAlarmReader),
    )


def get_deps() -> Deps:
    global _deps
    if _deps is None:
        _deps = build_aws_deps()
    return _deps


def set_deps(deps: Deps | None) -> None:
    global _deps
    _deps = deps
