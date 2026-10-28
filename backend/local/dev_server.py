#!/usr/bin/env python3
"""Local development API server (Python standard library only).

Runs the REAL Lambda handler code against in-memory DynamoDB/SNS/SQS
stand-ins, with a background thread that delivers queued messages to the
stock/payment/notify workers and sweeps the outbox. Results are SIMULATED:
nothing here proves the AWS deployment works.

    cd backend
    python3 local/dev_server.py            # http://127.0.0.1:8000

Seeded accounts (local only):
    admin@example.com     / Admin123!
    customer@example.com  / Customer123!
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "src"))
sys.path.insert(0, str(ROOT))

from order_system.handlers import authorizer  # noqa: E402
from order_system_local.environment import build_local_env  # noqa: E402
from order_system_local.routes import match  # noqa: E402

ALLOWED_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Order System local dev server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--stuck-seconds",
        type=int,
        default=20,
        help="seconds without progress before admin retry is offered (short for demos)",
    )
    parser.add_argument("--email", action="store_true", help="simulate the customer email SNS topic")
    args = parser.parse_args()

    env = build_local_env(
        email=args.email, stuck_order_seconds=args.stuck_seconds, outbox_min_age_seconds=5, retry_cooldown_seconds=5
    )
    env.seed_products()
    env.create_user("admin@example.com", "Admin123!", "Store Admin", role="admin")
    env.create_user("customer@example.com", "Customer123!", "Demo Customer")
    env.create_user("other@example.com", "Customer123!", "Other Customer")

    stop = threading.Event()

    def worker_loop() -> None:
        tick = 0
        while not stop.is_set():
            try:
                env.drain()
                tick += 1
                if tick % 20 == 0:
                    env.sweep_outbox()
            except Exception as exc:  # noqa: BLE001
                print(json.dumps({"level": "ERROR", "message": "local worker loop error", "error": str(exc)}))
            time.sleep(0.5)  # small delay so the UI can show PENDING -> PROCESSING -> CONFIRMED

    threading.Thread(target=worker_loop, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        server_version = "OrderSystemLocal/1.0"

        def _cors(self) -> None:
            origin = self.headers.get("Origin", "")
            if origin in ALLOWED_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header(
                    "Access-Control-Allow-Headers", "authorization,content-type,idempotency-key,x-correlation-id"
                )
                self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
                self.send_header("Access-Control-Expose-Headers", "x-correlation-id")
                self.send_header("Access-Control-Max-Age", "600")

        def _send(self, status: int, body: str, headers: dict[str, str] | None = None) -> None:
            data = body.encode()
            self.send_response(status)
            self._cors()
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            if not headers or "Content-Type" not in headers:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send(204, "")

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def do_PATCH(self) -> None:  # noqa: N802
            self._dispatch("PATCH")

        def _dispatch(self, method: str) -> None:
            url = urlsplit(self.path)
            if url.path == "/__local/status":
                self._send(200, json.dumps({"queues": env.bus.counts(), "mode": "local-simulation"}))
                return
            found = match(method, url.path)
            if not found:
                self._send(404, json.dumps({"message": "Not Found"}))
                return
            route_key, handler, needs_auth, params = found
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode() if length else None
            headers = {k.lower(): v for k, v in self.headers.items()}
            request_context: dict = {
                "requestId": f"local-{time.time_ns()}",
                "http": {"method": method, "path": url.path},
            }
            if needs_auth:
                # Runs the real Lambda Authorizer like API Gateway does: 401 without
                # a header, 403 when the authorizer denies, before the Lambda runs.
                if not headers.get("authorization"):
                    self._send(401, json.dumps({"message": "Unauthorized"}))
                    return
                decision = authorizer.handler({"headers": headers})
                if not decision["isAuthorized"]:
                    self._send(403, json.dumps({"message": "Forbidden"}))
                    return
                request_context["authorizer"] = {"lambda": decision["context"]}
            event = {
                "version": "2.0",
                "routeKey": route_key,
                "rawPath": url.path,
                "headers": headers,
                "queryStringParameters": dict(parse_qsl(url.query)) or None,
                "pathParameters": params or None,
                "body": body,
                "isBase64Encoded": False,
                "requestContext": request_context,
            }
            result = handler(event, None)
            self._send(int(result["statusCode"]), result.get("body", ""), result.get("headers"))

        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write(f"[http] {self.address_string()} {fmt % args}\n")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Local API (SIMULATED AWS) on http://{args.host}:{args.port}")
    print("Accounts: admin@example.com / Admin123!   customer@example.com / Customer123!")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
