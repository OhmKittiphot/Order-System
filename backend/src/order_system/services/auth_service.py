"""Registration and login (the "Auth Lambda" in the architecture diagram).

Passwords are stored only as PBKDF2 hashes in the Users table. Login issues
a short-lived access token (checked by the Lambda Authorizer on every
protected route) and a refresh token (accepted only by POST /auth/refresh).
The role in the token comes from the Users table, never from the request.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..utils.common import now_iso
from ..utils.errors import ServiceUnavailableError, UnauthorizedError, ValidationError
from ..utils.http import Principal
from ..utils.logging import get_logger
from ..utils.security import hash_password, sign_jwt, verify_jwt, verify_password
from .container import Deps

log = get_logger("auth-service")

# Compared against when the email is unknown so both paths cost one PBKDF2 run.
_DUMMY_HASH = hash_password("timing-equaliser")


class AuthService:
    def __init__(self, deps: Deps) -> None:
        self.deps = deps
        self.settings = deps.settings
        if not self.settings.jwt_secret:
            raise ServiceUnavailableError("Authentication is not configured")

    def register(self, email: str, password: str, display_name: str) -> dict[str, Any]:
        user_id = str(uuid.uuid4())
        now = now_iso()
        profile: dict[str, Any] = {
            "userId": user_id,
            "email": email,
            "displayName": display_name,
            "role": "customer",
            "createdAt": now,
            "updatedAt": now,
        }
        self.deps.users.create(profile, hash_password(password))
        subscription = "NOT_CONFIGURED"
        if self.deps.email is not None:
            try:
                self.deps.email.subscribe(email, user_id)
                subscription = "PENDING_CONFIRMATION"
            except Exception as exc:  # noqa: BLE001 - email is optional; registration must still succeed
                log.warning("email subscription failed", error=type(exc).__name__)
                subscription = "FAILED"
            self.deps.users.update_fields(user_id, {"emailSubscription": subscription})
        log.info("user registered", userId=user_id)
        return {"userId": user_id, "email": email, "displayName": display_name, "emailSubscription": subscription}

    def _session(self, profile: dict[str, Any]) -> dict[str, Any]:
        s = self.settings
        now = int(time.time())
        role = "admin" if profile.get("role") == "admin" else "customer"
        base = {"iss": s.jwt_issuer, "sub": profile["userId"], "iat": now}
        access = sign_jwt(
            {
                **base,
                "token_use": "access",
                "role": role,
                "email": profile.get("email", ""),
                "exp": now + s.access_token_ttl_seconds,
            },
            s.jwt_secret,
        )
        refresh = sign_jwt(
            {**base, "token_use": "refresh", "jti": uuid.uuid4().hex, "exp": now + s.refresh_token_ttl_seconds},
            s.jwt_secret,
        )
        return {
            "tokens": {"accessToken": access, "refreshToken": refresh, "expiresIn": s.access_token_ttl_seconds},
            "user": {
                "userId": profile["userId"],
                "email": profile.get("email", ""),
                "displayName": profile.get("displayName", ""),
                "role": role,
            },
        }

    def login(self, email: str, password: str) -> dict[str, Any]:
        credential = self.deps.users.get_credential(email)
        if credential is None:
            verify_password(password, _DUMMY_HASH)
            raise UnauthorizedError("Invalid email or password", code="INVALID_CREDENTIALS")
        if not verify_password(password, str(credential.get("passwordHash", ""))):
            raise UnauthorizedError("Invalid email or password", code="INVALID_CREDENTIALS")
        profile = self.deps.users.get(str(credential["ownerId"]))
        if profile is None:
            raise UnauthorizedError("Invalid email or password", code="INVALID_CREDENTIALS")
        session = self._session(profile)
        log.info("user logged in", userId=profile["userId"], role=session["user"]["role"])
        return session

    def refresh(self, refresh_token: Any) -> dict[str, Any]:
        if not isinstance(refresh_token, str) or not (20 <= len(refresh_token) <= 4096):
            raise ValidationError("refreshToken is required")
        s = self.settings
        claims = verify_jwt(refresh_token, s.jwt_secret, issuer=s.jwt_issuer, token_use="refresh")
        profile = self.deps.users.get(str(claims["sub"])) if claims else None
        if profile is None:
            raise UnauthorizedError("Invalid or expired refresh token")
        # Role is re-read from the table, so a promotion/demotion applies here.
        return self._session(profile)

    def me(self, principal: Principal) -> dict[str, Any]:
        profile = self.deps.users.get(principal.user_id) or {}
        return {
            "userId": principal.user_id,
            "email": profile.get("email", principal.email),
            "displayName": profile.get("displayName", ""),
            "role": principal.role,
        }
