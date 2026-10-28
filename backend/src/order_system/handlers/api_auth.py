"""Auth Lambda: POST /auth/register, POST /auth/login, POST /auth/refresh, GET /me."""

from __future__ import annotations

from typing import Any

from ..schemas.validation import validate_login, validate_register
from ..services.auth_service import AuthService
from ..services.container import get_deps
from ..utils.http import Request, Router

router = Router("auth-api")


@router.route("POST /auth/register")
def register(req: Request) -> tuple[int, Any]:
    email, password, name = validate_register(req.json())
    return 201, AuthService(get_deps()).register(email, password, name)


@router.route("POST /auth/login")
def login(req: Request) -> tuple[int, Any]:
    email, password = validate_login(req.json())
    return 200, AuthService(get_deps()).login(email, password)


@router.route("POST /auth/refresh")
def refresh(req: Request) -> tuple[int, Any]:
    body = req.json()
    return 200, AuthService(get_deps()).refresh(body.get("refreshToken"))


@router.route("GET /me")
def me(req: Request) -> tuple[int, Any]:
    return 200, AuthService(get_deps()).me(req.require_principal())


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    return router.handle(event)
