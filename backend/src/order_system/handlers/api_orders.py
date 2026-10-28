"""Order Lambda (customer API): POST /orders, GET /orders, GET /orders/{orderId},
GET /notifications. All routes require a verified JWT (API Gateway)."""

from __future__ import annotations

from typing import Any

from ..schemas.validation import validate_create_order, validate_idempotency_key
from ..services.container import get_deps
from ..services.order_service import OrderService
from ..utils.common import parse_limit, require_id
from ..utils.http import Request, Router

router = Router("orders-api")


@router.route("POST /orders")
def create_order(req: Request) -> tuple[int, Any]:
    principal = req.require_principal()
    deps = get_deps()
    key = validate_idempotency_key(req.headers.get("idempotency-key"))
    lines = validate_create_order(req.json(), deps.settings)
    return OrderService(deps).create_order(principal, key, lines, req.correlation_id)


@router.route("GET /orders")
def list_orders(req: Request) -> tuple[int, Any]:
    principal = req.require_principal()
    limit = parse_limit(req.query.get("limit"), default=20)
    return 200, OrderService(get_deps()).list_my_orders(principal, limit, req.query.get("nextToken"))


@router.route("GET /orders/{orderId}")
def get_order(req: Request) -> tuple[int, Any]:
    principal = req.require_principal()
    order_id = require_id(req.path_params.get("orderId"), "orderId")
    return 200, OrderService(get_deps()).get_order(principal, order_id)


@router.route("GET /notifications")
def list_notifications(req: Request) -> tuple[int, Any]:
    principal = req.require_principal()
    limit = parse_limit(req.query.get("limit"), default=20)
    return 200, OrderService(get_deps()).list_notifications(principal, limit, req.query.get("nextToken"))


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    return router.handle(event)
