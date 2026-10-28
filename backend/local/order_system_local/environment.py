"""Builds a complete in-memory environment (tables, bus, fakes) wired into
the real application code. Shared by unit tests and the dev server."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from order_system.config.settings import QueueConfig, Settings
from order_system.handlers import workers
from order_system.repositories.tables import LAYOUTS, physical_name
from order_system.services import outbox
from order_system.services.container import Deps, set_deps
from order_system.utils.common import now_iso

from .fakes import (
    FakeAlarmReader,
    FakeEmailNotifier,
    FakeQueueAdmin,
    InMemoryBus,
)
from .memory_dynamo import IndexDef, MemoryDynamoGateway, TableDef

SEED_FILE = Path(__file__).resolve().parents[2] / "seed" / "products.json"


def local_settings(**overrides: Any) -> Settings:
    queues = {
        name: QueueConfig(name, f"local://{name}", f"local://{name}", f"local://{name}-dlq", f"local://{name}-dlq")
        for name in ("stock", "payment", "notify")
    }
    base = Settings(
        environment="local",
        queues=queues,
        alarm_name_prefix="local-",
        stuck_order_seconds=120,
        jwt_secret=secrets.token_hex(32),  # per process; tokens die with the dev server
    )
    return replace(base, **overrides)


def make_tables(settings: Settings) -> list[TableDef]:
    tables = []
    for logical, layout in LAYOUTS.items():
        tables.append(
            TableDef(
                name=physical_name(settings, logical),
                partition_key=layout.partition_key,
                sort_key=layout.sort_key,
                indexes={name: IndexDef(pk, sk) for name, (pk, sk) in layout.indexes.items()},
            )
        )
    return tables


@dataclass
class LocalEnv:
    deps: Deps
    gw: MemoryDynamoGateway
    bus: InMemoryBus
    email: FakeEmailNotifier | None

    @property
    def handlers(self) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
        return {
            "stock": workers.stock_handler,
            "payment": workers.payment_handler,
            "notify": workers.notify_handler,
        }

    def drain(self) -> int:
        """Run all queued work (like Lambda event source mappings would)."""
        return self.bus.drain(self.handlers)

    def create_user(self, email: str, password: str, name: str, role: str = "customer") -> str:
        """Register through the real Auth service, then set the role the way
        scripts/create-admin.sh does in AWS."""
        from order_system.services.auth_service import AuthService

        user_id = AuthService(self.deps).register(email, password, name)["userId"]
        if role != "customer":
            self.deps.users.update_fields(user_id, {"role": role})
        return user_id

    def sweep_outbox(self) -> dict[str, int]:
        return outbox.sweep(self.deps)

    def seed_products(self, path: Path = SEED_FILE) -> list[str]:
        products = json.loads(path.read_text())
        ids = []
        now = now_iso()
        for p in products:
            pid = p["seedId"]
            item: dict[str, Any] = {
                "productId": pid,
                "name": p["name"],
                "description": p["description"],
                "priceMinor": p["priceMinor"],
                "currency": self.deps.settings.currency,
                "category": p["category"],
                "active": True,
                "catalogStatus": "ACTIVE",
                "createdAt": now,
                "updatedAt": now,
                "version": 1,
            }
            if p.get("testBehavior"):
                item["testBehavior"] = p["testBehavior"]
            self.deps.catalog.create_product(item, p["initialStock"])
            ids.append(pid)
        return ids


def build_local_env(*, email: bool = False, install: bool = True, **setting_overrides: Any) -> LocalEnv:
    settings = local_settings(customer_email_enabled=email, **setting_overrides)
    gw = MemoryDynamoGateway(make_tables(settings))
    bus = InMemoryBus()
    notifier = FakeEmailNotifier() if email else None
    deps = Deps(
        settings=settings,
        gw=gw,
        publisher=bus,
        email=notifier,
        queues=FakeQueueAdmin(bus),
        alarms=FakeAlarmReader(bus),
    )
    if install:
        set_deps(deps)
    return LocalEnv(deps=deps, gw=gw, bus=bus, email=notifier)
