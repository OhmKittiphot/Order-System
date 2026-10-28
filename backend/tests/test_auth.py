"""Auth Lambda (register/login/refresh/me) and the Lambda Authorizer."""

from __future__ import annotations

import time

from conftest import api
from order_system.handlers import authorizer
from order_system.utils.security import hash_password, sign_jwt, verify_password

PASSWORD = "Secret123"


def _register(email: str = "new@example.com", password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return api("POST", "/auth/register", body={"email": email, "password": password, "displayName": "New"})


def _login(email: str = "new@example.com", password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return api("POST", "/auth/login", body={"email": email, "password": password})


def _authorize(token: str) -> dict:
    return authorizer.handler({"headers": {"Authorization": f"Bearer {token}"}})


def test_password_hash_roundtrip():
    stored = hash_password(PASSWORD)
    assert PASSWORD not in stored
    assert verify_password(PASSWORD, stored)
    assert not verify_password("Wrong1234", stored)
    assert not verify_password(PASSWORD, "garbage")


def test_register_login_and_me(env):
    res = _register()
    assert res.status == 201
    user_id = res.data["userId"]

    session = _login().data
    assert session["user"] == {"userId": user_id, "email": "new@example.com", "displayName": "New", "role": "customer"}

    decision = _authorize(session["tokens"]["accessToken"])
    assert decision["isAuthorized"]
    assert decision["context"]["userId"] == user_id and decision["context"]["role"] == "customer"

    me = api("GET", "/me", user=(user_id, "customer")).data
    assert me["email"] == "new@example.com"


def test_password_hash_is_stored_not_password(env):
    user_id = _register().data["userId"]
    credential = env.deps.users.get_credential("new@example.com")
    assert credential["ownerId"] == user_id
    assert PASSWORD not in str(credential) and PASSWORD not in str(env.deps.users.get(user_id))


def test_duplicate_email_and_weak_password(env):
    _register()
    dup = _register()
    assert dup.status == 409 and dup.error["code"] == "EMAIL_EXISTS"
    weak = _register("weak@example.com", "alllowercase1")
    assert weak.status == 400 and weak.error["code"] == "WEAK_PASSWORD"


def test_wrong_password_and_unknown_email_look_the_same(env):
    _register()
    bad = _login(password="Wrong1234")
    unknown = _login(email="nobody@example.com")
    assert bad.status == unknown.status == 401
    assert bad.error == unknown.error


def test_admin_role_comes_from_users_table(env):
    env.create_user("boss@example.com", PASSWORD, "Boss", role="admin")
    session = _login("boss@example.com").data
    assert session["user"]["role"] == "admin"
    assert _authorize(session["tokens"]["accessToken"])["context"]["role"] == "admin"


def test_refresh_issues_new_access_token_and_rejects_access_token(env):
    _register()
    tokens = _login().data["tokens"]
    refreshed = api("POST", "/auth/refresh", body={"refreshToken": tokens["refreshToken"]})
    assert refreshed.status == 200
    assert _authorize(refreshed.data["tokens"]["accessToken"])["isAuthorized"]
    # an access token is not a refresh token, and vice versa
    assert api("POST", "/auth/refresh", body={"refreshToken": tokens["accessToken"]}).status == 401
    assert not _authorize(tokens["refreshToken"])["isAuthorized"]


def test_authorizer_rejects_bad_tokens(env):
    s = env.deps.settings
    now = int(time.time())
    good = {"iss": s.jwt_issuer, "sub": "u1", "token_use": "access", "role": "admin", "exp": now + 60}
    assert _authorize(sign_jwt(good, s.jwt_secret))["isAuthorized"]
    assert not _authorize(sign_jwt({**good, "exp": now - 1}, s.jwt_secret))["isAuthorized"]  # expired
    assert not _authorize(sign_jwt(good, "another-secret"))["isAuthorized"]  # forged
    assert not _authorize(sign_jwt({**good, "iss": "someone-else"}, s.jwt_secret))["isAuthorized"]
    header, payload, _ = sign_jwt(good, s.jwt_secret).split(".")
    assert not _authorize(f"{header}.{payload}.")["isAuthorized"]  # stripped signature
    assert not _authorize("not-a-jwt")["isAuthorized"]
    assert not authorizer.handler({"headers": {}})["isAuthorized"]
    # an unexpected role value never becomes admin
    odd = _authorize(sign_jwt({**good, "role": "superuser"}, s.jwt_secret))
    assert odd["context"]["role"] == "customer"
