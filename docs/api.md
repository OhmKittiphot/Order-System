# API Reference

The machine-readable spec is [`backend/openapi.yaml`](../backend/openapi.yaml) (checked against the deployed
routes by `tests/test_consistency.py`). This page summarises it with examples.

Base URL: `terraform output -raw api_url` (AWS) or `http://127.0.0.1:8000` (local dev server).

## Conventions

* JSON in, JSON out. Success: `{"data": …, "correlationId": "…"}`. Error: `{"error": {"code", "message", "details"?}, "correlationId"}`.
* `Authorization: Bearer <accessToken>` on protected routes. Missing/invalid/expired token → **401** from API Gateway.
  Valid token without the `admins` group on `/admin/*` → **403**.
* `X-Correlation-Id` is returned on every response (send your own to trace a request in CloudWatch Logs).
* Unknown body fields are rejected (400) — clients cannot send `price`, `total`, `role` or `status`.
* Pagination: `?limit=20&nextToken=<opaque>`; `nextToken: null` means last page.
* Money in minor units: `129000` = 1,290.00 THB.

| Status | Meaning |
|---|---|
| 200 / 201 | OK / created |
| 202 | Accepted for asynchronous processing (orders, retries, redrive) |
| 400 | Validation error (`VALIDATION_ERROR`, `INVALID_PRODUCTS`, `IDEMPOTENCY_KEY_REQUIRED`, `WEAK_PASSWORD`) |
| 401 | Not signed in / bad credentials (`INVALID_CREDENTIALS`) |
| 403 | Not allowed (`FORBIDDEN`) |
| 404 | Not found (also returned for another customer's order) |
| 409 | Conflict (`IDEMPOTENCY_KEY_REUSED`, `NOT_RETRYABLE`, `RETRY_CONFLICT`, `NEGATIVE_STOCK`, `EMAIL_EXISTS`) |
| 429 | Throttled by the API stage |
| 500 / 503 | Internal / temporarily unavailable (no internals are leaked) |

## Endpoints

| Method & path | Auth | Description |
|---|---|---|
| `POST /auth/register` | – | Create a customer account |
| `POST /auth/login` | – | Get tokens + profile |
| `POST /auth/refresh` | – | Refresh tokens |
| `GET /me` | JWT | Current profile |
| `GET /products` | – | Active products with stock |
| `GET /products/{productId}` | – | Product detail |
| `POST /orders` | JWT | Place order (header `Idempotency-Key`) |
| `GET /orders` | JWT | My order history |
| `GET /orders/{orderId}` | JWT | Order status (own orders; admins any) |
| `GET /notifications` | JWT | My notifications |
| `GET /admin/stats` | admin | Dashboard counts |
| `GET /admin/orders?status=` | admin | All orders, filter by status |
| `GET /admin/orders/{orderId}` | admin | Detail incl. payments + retry decision |
| `POST /admin/orders/{orderId}/retry` | admin | Retry eligible order |
| `POST /admin/orders/{orderId}/cancel` | admin | Cancel, releasing reserved stock |
| `GET /admin/products` | admin | All products with stock |
| `POST /admin/products` | admin | Create product |
| `GET /admin/products/{productId}` | admin | Product detail |
| `PATCH /admin/products/{productId}` | admin | Edit product |
| `PATCH /admin/products/{productId}/stock` | admin | Set/adjust stock |
| `GET /admin/dlq-status` | admin | Queues, DLQs, alarms, stuck/failed orders |
| `POST /admin/dlq/{queue}/redrive` | admin | Redrive `stock`, `payment` or `notify` DLQ |

## Examples

```bash
API=$(terraform -chdir=terraform output -raw api_url)   # or http://127.0.0.1:8000
```

### Register and sign in
```bash
curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"ann@example.com","password":"Passw0rd!","displayName":"Ann"}'
# 201 {"data":{"userId":"5e1…","email":"ann@example.com","displayName":"Ann","confirmed":true,"emailSubscription":"NOT_CONFIGURED"},…}

TOKEN=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"ann@example.com","password":"Passw0rd!"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["tokens"]["accessToken"])')
```

### Place an order
```bash
curl -s -X POST $API/orders -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-order-0001' \
  -d '{"items":[{"productId":"prd_seed_earbuds","quantity":2}]}'
```
```json
{
  "data": {
    "orderId": "ord_9bfcfa9aaece46928f8e67fa94d105d4",
    "customerId": "5e1…",
    "items": [{"productId": "prd_seed_earbuds", "name": "Wireless Earbuds", "unitPriceMinor": 129000, "quantity": 2, "lineTotalMinor": 258000}],
    "itemCount": 2, "totalMinor": 258000, "currency": "THB",
    "status": "PENDING", "inventoryStatus": "PENDING", "paymentStatus": "PENDING", "notificationStatus": "PENDING",
    "createdAt": "2026-10-27T08:25:41.120Z", "updatedAt": "2026-10-27T08:25:41.120Z", "attempt": 0, "retryCount": 0,
    "message": "Order accepted and is being processed"
  },
  "correlationId": "7c1d…"
}
```
Sending the same request again returns **200** with the same `orderId` and `"idempotentReplay": true`.
The same key with different items returns **409 `IDEMPOTENCY_KEY_REUSED`**.

### Poll the status
```bash
curl -s $API/orders/ord_9bfc… -H "Authorization: Bearer $TOKEN"
# … "status":"CONFIRMED","inventoryStatus":"COMMITTED","paymentStatus":"SUCCEEDED","notificationStatus":"SENT",
#     "history":[{"at":"…","event":"OrderCreated",…},{"event":"InventoryReserved",…},{"event":"PaymentSucceeded",…},{"event":"CustomerNotified",…}]
```

### Errors
```json
{"error": {"code": "VALIDATION_ERROR", "message": "Unknown fields in request", "details": {"fields": ["priceMinor"]}}, "correlationId": "…"}
{"error": {"code": "NOT_RETRYABLE", "message": "Payment was declined; the customer must place a new order",
           "details": {"retryable": false, "action": null, "reason": "…", "category": "PAYMENT_DECLINED"}}, "correlationId": "…"}
```

### Admin: restock and retry
```bash
curl -s -X PATCH $API/admin/products/prd_seed_mug/stock -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"mode":"adjust","quantity":10,"reason":"delivery"}'
curl -s -X POST $API/admin/orders/ord_…/retry -H "Authorization: Bearer $ADMIN_TOKEN"
# 202 {"data":{"orderId":"ord_…","action":"RESTART","attempt":1,"status":"PENDING","eventPublished":true,"message":"Stock is now available; …"}}
```

## Events (SNS `order-events`, SQS raw delivery)

```json
{"eventId":"evt_…","eventType":"OrderPlaced","schemaVersion":"1.0","occurredAt":"2026-10-27T08:25:41.130Z",
 "orderId":"ord_…","customerId":"5e1…","attempt":0,"correlationId":"7c1d…"}
```
`eventType` ∈ `OrderPlaced`, `InventoryReserved`, `OrderConfirmed`, `OrderFailed`; also sent as the SNS message
attribute `eventType` used by the subscription filter policies. Events contain identifiers only — no prices,
emails, tokens or payment data. Consumers also accept SNS-envelope format if raw delivery is turned off.
