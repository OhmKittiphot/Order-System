"""Lambda Authorizer ("verify JWT" in the architecture diagram).

API Gateway (HTTP API, simple responses) calls this before every protected
route. It verifies the access token issued by the Auth Lambda and passes the
verified identity to the target Lambda as
``requestContext.authorizer.lambda`` (see ``utils.http.principal_from_event``).
A missing ``Authorization`` header never reaches here: the gateway answers 401.
"""

from __future__ import annotations

from typing import Any

from ..services.container import get_deps
from ..utils.logging import get_logger
from ..utils.security import verify_jwt

log = get_logger("authorizer")

DENY: dict[str, Any] = {"isAuthorized": False}


def authorize(token: str) -> dict[str, Any]:
    s = get_deps().settings
    claims = verify_jwt(token, s.jwt_secret, issuer=s.jwt_issuer, token_use="access")
    if claims is None:
        log.info("token rejected")
        return DENY
    return {
        "isAuthorized": True,
        "context": {
            "userId": str(claims["sub"]),
            "role": "admin" if claims.get("role") == "admin" else "customer",
            "email": str(claims.get("email", "")),
        },
    }


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    headers = {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}
    auth = headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return DENY
    return authorize(auth.removeprefix("Bearer ").strip())
