# Database Design (DynamoDB)

All tables use on-demand capacity (`PAY_PER_REQUEST`), are encrypted at rest (DynamoDB default AWS-owned key)
and are named `<project>-<env>-<suffix>-<table>`. Key layout is defined once in
`backend/src/order_system/repositories/tables.py` and in `terraform/dynamodb.tf`;
`backend/tests/test_consistency.py` fails if they differ.

Numbers are integers only. Money is stored in minor units (`priceMinor = 129000` → 1,290.00 THB), which
avoids floating-point rounding. Timestamps are UTC ISO 8601 with milliseconds (`2026-10-27T08:00:00.000Z`),
so they sort correctly as strings in sort keys.

## Tables

### Orders — PK `orderId`
| Attribute | Example | Notes |
|---|---|---|
| `orderId` | `ord_5f1c…` | uuid4 hex, prefixed |
| `entityType` | `ORDER` | constant, key of `entity-index` |
| `customerId` | user's `userId` | from the token verified by the Lambda Authorizer, never from the body |
| `items` | list of `{productId, name, unitPriceMinor, quantity, lineTotalMinor[, testBehavior]}` | price snapshot taken server-side |
| `itemCount`, `totalMinor`, `currency` | `3`, `258000`, `THB` | |
| `status`, `inventoryStatus`, `paymentStatus`, `notificationStatus` | see `order-workflow.md` | |
| `failureReason`, `failureCategory` | | only when failed |
| `attempt` | `0` | retry generation (API shows it as `retryCount`) |
| `version` | `4` | +1 on every state change (optimistic locking) |
| `processingAttempts` | `2` | worker invocations incl. SQS redeliveries (diagnostic) |
| `idempotencyKey`, `correlationId` | | |
| `history` | list of `{at, event, detail, status}` | timeline shown in the UI |
| `outboxStatus`, `outboxEventType`, `outboxToken` | `PENDING_PUBLISH` | present only while an event is unpublished |
| `lastPublishedAt`, `lastRetryAt`, `lastRetryBy`, `cancelledBy` | | |
| `createdAt`, `updatedAt` | ISO 8601 | |

| GSI | PK | SK | Purpose |
|---|---|---|---|
| `customer-index` | `customerId` | `createdAt` | customer order history (newest first) |
| `entity-index` | `entityType` | `createdAt` | admin list of all orders |
| `status-index` | `status` | `createdAt` | admin status filter, dashboard counts, stuck-order detection |
| `outbox-index` (sparse) | `outboxStatus` | `createdAt` | unpublished events for the outbox publisher |

### Products — PK `productId`
`name, description, priceMinor, currency, category, imageUrl?, active, catalogStatus (ACTIVE|INACTIVE), testBehavior?, version, createdAt, updatedAt, createdBy`

| GSI | PK | SK | Purpose |
|---|---|---|---|
| `catalog-index` | `catalogStatus` | `name` | public catalog sorted by name, no scan |

### Inventory — PK `productId`
`available, reserved, sold, version, updatedAt`. Kept separate from Products so price edits never contend
with stock reservations and every stock write is a small conditional update.

### Payments — PK `orderId`, SK `attempt` (N)
`paymentId, status (SUCCEEDED|FAILED), amountMinor, currency, provider = SIMULATED, reason?, createdAt`.
One record per order attempt; `attribute_not_exists` makes double charging impossible.

### Notifications — PK `notificationId`
`notificationId = ntf_<orderId>_<attempt>_<eventType>` (deterministic → dedupe), `customerId, orderId, type,
orderStatus, title, message, channels, emailStatus (NOT_CONFIGURED|PENDING|ACCEPTED_BY_SNS|FAILED), emailAttempts,
snsMessageId?, createdAt`. GSI `customer-index` (`customerId`, `createdAt`).

### Users — PK `userId`
Two item types, written together in one transaction at registration:

* **Profile** `userId = <uuid4>`: `entityType = USER, email, displayName, role (customer|admin), emailSubscription?, createdAt, updatedAt`.
* **Credential** `userId = EMAIL#<lower-case email>`: `entityType = CREDENTIAL, ownerId, passwordHash (pbkdf2_sha256$<iterations>$<salt>$<hash>), createdAt`.
  The conditional put on this key makes emails unique; login is a single `GetItem`. The hash is never returned by the API.

### Idempotency — PK `idempotencyId` = `<customerId>#<Idempotency-Key>`, TTL `expiresAt`
`orderId, requestHash (sha256 of the normalised items), createdAt, expiresAt (epoch seconds, default +24 h)`.

## Access patterns

| # | Use case | Operation | Table / index | Scan? |
|---|---|---|---|---|
| 1 | Browse products | Query `catalogStatus = ACTIVE` + BatchGet inventory | Products `catalog-index`, Inventory | No |
| 2 | Product detail | GetItem ×2 | Products, Inventory | No |
| 3 | Place order | BatchGet products, TransactWrite (idempotency + order), UpdateItem (clear outbox) | Products, Idempotency, Orders | No |
| 4 | Order status | GetItem | Orders | No |
| 5 | Order history | Query `customerId` desc | Orders `customer-index` | No |
| 6 | Notifications | Query `customerId` desc | Notifications `customer-index` | No |
| 7 | Reserve stock | TransactWrite (inventory ×n + order) | Inventory, Orders | No |
| 8 | Payment | TransactWrite (payment + order + inventory ×n) | Payments, Orders, Inventory | No |
| 9 | Admin: all orders / by status | Query desc | Orders `entity-index` / `status-index` | No |
| 10 | Admin: dashboard counts | Query `Select=COUNT` per status | Orders `status-index` | No |
| 11 | Admin: product list, low stock | Scan (admin only, small catalogue) | Products, Inventory | Yes – documented |
| 12 | Outbox sweep | Query `outboxStatus = PENDING_PUBLISH AND createdAt <= cutoff` | Orders `outbox-index` | No |
| 13 | Stuck orders | Query `status` + filter `updatedAt <= cutoff` | Orders `status-index` | No |

## Scaling notes (beyond the lab)

* `entity-index` puts all orders in one partition key. Fine for a lab; at high volume, shard it
  (`ORDER#<0-9>`) or partition by day (`ORDER#2026-10-27`).
* `status-index` concentrates writes on a few values; same sharding applies.
* Admin product scans should become a GSI query once the catalogue is large.
* Transactions are limited to 100 items, hence `MAX_ORDER_ITEMS = 20` lines (payment = 2 + 20 items).
* PITR is enabled on Orders, Inventory and Payments (`enable_point_in_time_recovery`).
