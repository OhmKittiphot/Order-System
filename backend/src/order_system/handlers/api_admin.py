"""Admin API. API Gateway verifies the JWT; every route here additionally
requires ``role = admin`` from the verified token (403 otherwise)."""

from __future__ import annotations

from typing import Any

from ..schemas.validation import (
    validate_product_create,
    validate_product_update,
    validate_queue_name,
    validate_status_filter,
    validate_stock_change,
)
from ..services.admin_service import AdminService
from ..services.catalog_service import CatalogService
from ..services.container import get_deps
from ..services.retry_service import RetryService
from ..utils.common import parse_limit, require_id
from ..utils.http import Request, Router

router = Router("admin-api")


def _admin(req: Request) -> str:
    return req.require_admin().user_id


@router.route("GET /admin/orders")
def list_orders(req: Request) -> tuple[int, Any]:
    _admin(req)
    status = validate_status_filter(req.query.get("status"))
    limit = parse_limit(req.query.get("limit"), default=25)
    return 200, AdminService(get_deps()).list_orders(limit, req.query.get("nextToken"), status)


@router.route("GET /admin/orders/{orderId}")
def get_order(req: Request) -> tuple[int, Any]:
    _admin(req)
    return 200, AdminService(get_deps()).order_detail(require_id(req.path_params.get("orderId"), "orderId"))


@router.route("POST /admin/orders/{orderId}/retry")
def retry_order(req: Request) -> tuple[int, Any]:
    admin_id = _admin(req)
    order_id = require_id(req.path_params.get("orderId"), "orderId")
    return 202, RetryService(get_deps()).retry(order_id, admin_id, req.correlation_id)


@router.route("POST /admin/orders/{orderId}/cancel")
def cancel_order(req: Request) -> tuple[int, Any]:
    admin_id = _admin(req)
    order_id = require_id(req.path_params.get("orderId"), "orderId")
    return 200, RetryService(get_deps()).cancel(order_id, admin_id)


@router.route("GET /admin/products")
def list_products(req: Request) -> tuple[int, Any]:
    _admin(req)
    limit = parse_limit(req.query.get("limit"), default=100)
    return 200, CatalogService(get_deps()).admin_list(limit, req.query.get("nextToken"))


@router.route("POST /admin/products")
def create_product(req: Request) -> tuple[int, Any]:
    admin_id = _admin(req)
    data = validate_product_create(req.json())
    return 201, CatalogService(get_deps()).create(data, admin_id)


@router.route("GET /admin/products/{productId}")
def get_product(req: Request) -> tuple[int, Any]:
    _admin(req)
    return 200, CatalogService(get_deps()).admin_get(require_id(req.path_params.get("productId"), "productId"))


@router.route("PATCH /admin/products/{productId}")
def update_product(req: Request) -> tuple[int, Any]:
    _admin(req)
    product_id = require_id(req.path_params.get("productId"), "productId")
    return 200, CatalogService(get_deps()).update(product_id, validate_product_update(req.json()))


@router.route("PATCH /admin/products/{productId}/stock")
def change_stock(req: Request) -> tuple[int, Any]:
    admin_id = _admin(req)
    product_id = require_id(req.path_params.get("productId"), "productId")
    mode, qty, reason = validate_stock_change(req.json())
    return 200, CatalogService(get_deps()).change_stock(product_id, mode, qty, reason, admin_id)


@router.route("GET /admin/stats")
def stats(req: Request) -> tuple[int, Any]:
    _admin(req)
    return 200, AdminService(get_deps()).stats()


@router.route("GET /admin/dlq-status")
def dlq_status(req: Request) -> tuple[int, Any]:
    _admin(req)
    return 200, AdminService(get_deps()).dlq_status()


@router.route("POST /admin/dlq/{queue}/redrive")
def redrive(req: Request) -> tuple[int, Any]:
    _admin(req)
    queue = validate_queue_name(req.path_params.get("queue", ""))
    return 202, RetryService(get_deps()).redrive(queue)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    return router.handle(event)
