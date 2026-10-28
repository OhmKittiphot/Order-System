"""Public product catalog: GET /products, GET /products/{productId}."""

from __future__ import annotations

from typing import Any

from ..services.catalog_service import CatalogService
from ..services.container import get_deps
from ..utils.common import parse_limit, require_id
from ..utils.http import Request, Router

router = Router("products-api")


@router.route("GET /products")
def list_products(req: Request) -> tuple[int, Any]:
    limit = parse_limit(req.query.get("limit"), default=24)
    return 200, CatalogService(get_deps()).list_products(limit, req.query.get("nextToken"))


@router.route("GET /products/{productId}")
def get_product(req: Request) -> tuple[int, Any]:
    product_id = require_id(req.path_params.get("productId"), "productId")
    return 200, CatalogService(get_deps()).get_product(product_id)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    return router.handle(event)
