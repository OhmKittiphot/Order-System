#!/usr/bin/env python3
"""End-to-end test against a running API (deployed on AWS or the local dev server).

Python standard library only. It CREATES users and orders, so it only runs
with --allow-mutations. The slow DLQ scenario (several minutes on AWS,
because SQS waits the visibility timeout between receives) needs --include-dlq.

Examples:
    # deployed stack (API URL read from terraform output)
    python3 scripts/e2e_test.py --allow-mutations --admin-email admin@example.com --admin-password '...'
    # local dev server
    python3 scripts/e2e_test.py --api-url http://127.0.0.1:8000 --allow-mutations \
        --admin-email admin@example.com --admin-password 'Admin123!' --include-dlq --stuck-seconds 20
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[str, bool, str]] = []


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: object = None, token: str | None = None,
             headers: dict[str, str] | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        h = {"Content-Type": "application/json", "X-Correlation-Id": f"e2e-{uuid.uuid4().hex[:12]}"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - URL supplied by the operator
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as err:
            raw = err.read()
            try:
                return err.code, json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return err.code, {"raw": raw.decode(errors="replace")}


def check(name: str, condition: bool, detail: str = "") -> bool:
    RESULTS.append((name, condition, detail))
    mark = "\033[32mPASS\033[0m" if condition else "\033[31mFAIL\033[0m"
    print(f"[{mark}] {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def wait_for(fn, timeout: float, interval: float = 2.0):  # type: ignore[no-untyped-def]
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    return last


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api-url")
    p.add_argument("--admin-email", default=os.environ.get("ADMIN_EMAIL"))
    p.add_argument("--admin-password", default=os.environ.get("ADMIN_PASSWORD"))
    p.add_argument("--allow-mutations", action="store_true", help="required: creates users, orders and stock changes")
    p.add_argument("--include-dlq", action="store_true", help="also run the transient-failure -> DLQ -> retry scenario")
    p.add_argument("--stuck-seconds", type=int, default=120, help="STUCK_ORDER_SECONDS configured on the backend")
    p.add_argument("--timeout", type=int, default=120, help="seconds to wait for normal processing")
    args = p.parse_args()

    if not args.allow_mutations:
        print("Refusing to run without --allow-mutations (this test creates data).")
        return 2
    base = args.api_url or subprocess.check_output(
        ["terraform", f"-chdir={ROOT / 'terraform'}", "output", "-raw", "api_url"], text=True).strip()
    api = Api(base)
    print(f"API: {base}\n")
    tag = uuid.uuid4().hex[:8]
    password = f"E2e-{tag}-Pw1"

    # 1. catalogue
    status, body = api.call("GET", "/products?limit=50")
    products = {x["productId"]: x for x in body.get("data", {}).get("items", [])}
    check("public product listing", status == 200 and len(products) > 0, f"{status} {body}")

    # 2. users
    tokens = {}
    for who in ("a", "b"):
        email = f"e2e-{tag}-{who}@example.com"
        s, b = api.call("POST", "/auth/register", {"email": email, "password": password, "displayName": f"E2E {who}"})
        check(f"register customer {who}", s == 201, f"{s} {b}")
        s, b = api.call("POST", "/auth/login", {"email": email, "password": password})
        ok = check(f"login customer {who}", s == 200 and b["data"]["user"]["role"] == "customer", f"{s} {b}")
        if not ok:
            return summary()
        tokens[who] = b["data"]["tokens"]["accessToken"]

    # 3. authentication boundary
    s, _ = api.call("GET", "/orders")
    check("unauthenticated request rejected (401)", s == 401, str(s))

    # 4. happy path + idempotency
    key = f"e2e-{tag}-order-1"
    order_body = {"items": [{"productId": "prd_seed_hub", "quantity": 1}]}
    s, b = api.call("POST", "/orders", order_body, tokens["a"], {"Idempotency-Key": key})
    check("create order returns 202 PENDING", s == 202 and b["data"]["status"] == "PENDING", f"{s} {b}")
    order_id = b.get("data", {}).get("orderId", "")
    s2, b2 = api.call("POST", "/orders", order_body, tokens["a"], {"Idempotency-Key": key})
    check("idempotent retry returns the same order", s2 == 200 and b2["data"]["orderId"] == order_id, f"{s2} {b2}")

    def order_state(oid: str, token: str) -> dict:
        return api.call("GET", f"/orders/{oid}", token=token)[1].get("data", {})

    final = wait_for(lambda: (o := order_state(order_id, tokens["a"])) and o.get("notificationStatus") == "SENT" and o,
                     args.timeout)
    check("order processed to CONFIRMED asynchronously",
          bool(final) and final["status"] == "CONFIRMED" and final["paymentStatus"] == "SUCCEEDED",
          json.dumps(final)[:300])
    notes = api.call("GET", "/notifications", token=tokens["a"])[1].get("data", {}).get("items", [])
    check("customer notification recorded", any(n["orderId"] == order_id for n in notes), str(notes)[:300])

    # 5. authorization boundaries
    s, _ = api.call("GET", f"/orders/{order_id}", token=tokens["b"])
    check("customer cannot read another customer's order", s in (403, 404), str(s))
    s, _ = api.call("GET", "/admin/orders", token=tokens["b"])
    check("customer cannot call admin endpoints (403)", s == 403, str(s))

    # 6. payment failure with stock compensation
    before = api.call("GET", "/products/prd_test_decline")[1]["data"]["available"]
    s, b = api.call("POST", "/orders", {"items": [{"productId": "prd_test_decline", "quantity": 1}]}, tokens["a"],
                    {"Idempotency-Key": f"e2e-{tag}-decline"})
    decline_id = b.get("data", {}).get("orderId", "")
    o = wait_for(lambda: (x := order_state(decline_id, tokens["a"])) and x.get("status") == "FAILED" and x, args.timeout)
    after = api.call("GET", "/products/prd_test_decline")[1]["data"]["available"]
    check("declined payment fails the order and releases stock",
          bool(o) and o.get("paymentStatus") == "FAILED" and o.get("inventoryStatus") == "RELEASED" and before == after,
          f"{o} before={before} after={after}")

    # 7. out of stock
    hub = api.call("GET", "/products/prd_seed_stand")[1].get("data", {})
    qty = min(99, int(hub.get("available", 0)) + 1)
    s, b = api.call("POST", "/orders", {"items": [{"productId": "prd_seed_stand", "quantity": qty}]}, tokens["b"],
                    {"Idempotency-Key": f"e2e-{tag}-oos"})
    oos_id = b.get("data", {}).get("orderId", "")
    o = wait_for(lambda: (x := order_state(oos_id, tokens["b"])) and x.get("status") == "FAILED" and x, args.timeout)
    check("insufficient stock fails the order (OUT_OF_STOCK)", bool(o) and o.get("inventoryStatus") == "OUT_OF_STOCK",
          str(o)[:300])

    # 8. admin
    if not (args.admin_email and args.admin_password):
        print("\n(admin checks skipped: pass --admin-email/--admin-password)")
        return summary()
    s, b = api.call("POST", "/auth/login", {"email": args.admin_email, "password": args.admin_password})
    if not check("admin login", s == 200 and b["data"]["user"]["role"] == "admin", f"{s} {b}"):
        return summary()
    admin = b["data"]["tokens"]["accessToken"]
    s, b = api.call("GET", "/admin/stats", token=admin)
    check("admin dashboard stats", s == 200 and b["data"]["orders"]["total"] >= 3, f"{s}")
    s, b = api.call("GET", "/admin/orders?status=FAILED&limit=50", token=admin)
    check("admin can list failed orders", s == 200 and any(x["orderId"] == oos_id for x in b["data"]["items"]), f"{s}")
    s, b = api.call("POST", f"/admin/orders/{oos_id}/retry", token=admin)
    check("business failure is not retried before restock (409)", s == 409, f"{s} {b}")
    s, b = api.call("GET", "/admin/dlq-status", token=admin)
    check("admin operational status", s == 200 and len(b["data"]["queues"]) == 3, f"{s}")

    # 9. DLQ scenario
    if args.include_dlq:
        s, b = api.call("POST", "/orders", {"items": [{"productId": "prd_test_flaky", "quantity": 1}]}, tokens["a"],
                        {"Idempotency-Key": f"e2e-{tag}-flaky"})
        flaky_id = b.get("data", {}).get("orderId", "")
        print("   waiting for the payment message to reach the DLQ (on AWS this takes ~3x the visibility timeout)...")

        def in_dlq() -> bool:
            st = api.call("GET", "/admin/dlq-status", token=admin)[1].get("data", {})
            pay = next((q for q in st.get("queues", []) if q["name"] == "payment"), {})
            return pay.get("dlqVisible", 0) > 0

        check("transient failure moved to the payment DLQ", bool(wait_for(in_dlq, 900, 10)))
        time.sleep(args.stuck_seconds + 2)
        s, b = api.call("POST", f"/admin/orders/{flaky_id}/retry", token=admin)
        check("admin retry of the stuck order accepted", s == 202, f"{s} {b}")
        o = wait_for(lambda: (x := order_state(flaky_id, tokens["a"])) and x.get("status") == "CONFIRMED" and x,
                     args.timeout)
        check("retried order confirmed", bool(o), str(o)[:300])
    return summary()


def summary() -> int:
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
