"""API Gateway HTTP API (payload v2) helpers: request parsing, auth context,
responses and a tiny route-key router shared by all API Lambdas."""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .errors import AppError, ForbiddenError, UnauthorizedError, ValidationError
from .logging import get_logger, log_context

MAX_BODY_BYTES = 64 * 1024
_CID_RE = re.compile(r"^[A-Za-z0-9\-_.:]{8,128}$")


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str = "customer"
    email: str = ""

    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass
class Request:
    route_key: str
    method: str
    path: str
    headers: dict[str, str]
    query: dict[str, str]
    path_params: dict[str, str]
    raw_body: str | None
    correlation_id: str
    principal: Principal | None = None
    _json: Any = field(default=None, repr=False)

    def json(self) -> dict[str, Any]:
        if self._json is not None:
            return self._json
        if self.raw_body is None or self.raw_body == "":
            raise ValidationError("Request body is required")
        if len(self.raw_body.encode()) > MAX_BODY_BYTES:
            raise ValidationError("Request body is too large")
        try:
            data = json.loads(self.raw_body)
        except json.JSONDecodeError as exc:
            raise ValidationError("Request body must be valid JSON") from exc
        if not isinstance(data, dict):
            raise ValidationError("Request body must be a JSON object")
        self._json = data
        return data

    def require_principal(self) -> Principal:
        if self.principal is None:
            raise UnauthorizedError("Authentication is required")
        return self.principal

    def require_admin(self) -> Principal:
        principal = self.require_principal()
        if not principal.is_admin():
            raise ForbiddenError("Administrator role is required")
        return principal


def principal_from_event(event: dict[str, Any]) -> Principal | None:
    """The identity is only present when the Lambda Authorizer verified the
    access token (signature, issuer, expiry). We never read roles from the
    request body or from unverified headers."""
    ctx = event.get("requestContext", {}).get("authorizer", {}).get("lambda")
    if not ctx or not ctx.get("userId"):
        return None
    return Principal(
        user_id=str(ctx["userId"]),
        role="admin" if ctx.get("role") == "admin" else "customer",
        email=str(ctx.get("email", "")),
    )


def parse_event(event: dict[str, Any]) -> Request:
    headers = {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}
    ctx = event.get("requestContext", {})
    supplied = headers.get("x-correlation-id", "")
    correlation_id = supplied if _CID_RE.match(supplied) else str(ctx.get("requestId") or "local")
    body = event.get("body")
    if body is not None and event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", errors="replace")
    http = ctx.get("http", {})
    return Request(
        route_key=str(event.get("routeKey", "")),
        method=str(http.get("method", "")).upper(),
        path=str(http.get("path", event.get("rawPath", ""))),
        headers=headers,
        query={str(k): str(v) for k, v in (event.get("queryStringParameters") or {}).items()},
        path_params={str(k): str(v) for k, v in (event.get("pathParameters") or {}).items()},
        raw_body=body,
        correlation_id=correlation_id,
        principal=principal_from_event(event),
    )


def response(
    status: int, body: Any, correlation_id: str, extra_headers: dict[str, str] | None = None
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Correlation-Id": correlation_id,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if extra_headers:
        headers.update(extra_headers)
    return {"statusCode": status, "headers": headers, "body": json.dumps(body, default=str)}


def ok(data: Any, correlation_id: str, status: int = 200) -> dict[str, Any]:
    return response(status, {"data": data, "correlationId": correlation_id}, correlation_id)


def error_response(err: AppError, correlation_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": err.code, "message": err.message}
    if err.details is not None:
        payload["details"] = err.details
    return response(err.status_code, {"error": payload, "correlationId": correlation_id}, correlation_id)


Handler = Callable[[Request], tuple[int, Any]]


class Router:
    """Dispatch on API Gateway ``routeKey`` (e.g. ``"GET /orders/{orderId}"``)."""

    def __init__(self, service: str) -> None:
        self.routes: dict[str, Handler] = {}
        self.log = get_logger(service)

    def route(self, route_key: str) -> Callable[[Handler], Handler]:
        def register(fn: Handler) -> Handler:
            self.routes[route_key] = fn
            return fn

        return register

    def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        try:
            request = parse_event(event)
        except AppError as err:
            return error_response(err, "unknown")
        with log_context(
            correlationId=request.correlation_id,
            route=request.route_key,
            userId=request.principal.user_id if request.principal else None,
        ):
            handler = self.routes.get(request.route_key)
            if handler is None:
                return error_response(AppError("Route not found", code="ROUTE_NOT_FOUND"), request.correlation_id) | {
                    "statusCode": 404
                }
            try:
                status, data = handler(request)
                self.log.info("request completed", status=status)
                return ok(data, request.correlation_id, status)
            except AppError as err:
                level = self.log.warning if err.status_code < 500 else self.log.error
                level("request failed", status=err.status_code, code=err.code, error=err.message)
                return error_response(err, request.correlation_id)
            except Exception as exc:  # noqa: BLE001 - last-resort guard, no stack trace to client
                self.log.error("unhandled error", errorType=type(exc).__name__, error=str(exc))
                return error_response(AppError("An internal error occurred"), request.correlation_id)
