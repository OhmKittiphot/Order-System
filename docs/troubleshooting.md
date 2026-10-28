# Troubleshooting

Every API response and log line carries a **correlation id**. Copy it from the UI error ("Reference: …"),
the `X-Correlation-Id` response header or the API access log, then search all function logs:

```bash
P=$(terraform -chdir=terraform output -raw name_prefix)
for f in auth products orders admin stock payment notify outbox; do
  aws logs filter-log-events --log-group-name /aws/lambda/$P-$f --filter-pattern '"<correlation-id>"' \
    --query 'events[].message' --output text; done
```
Useful CloudWatch Logs Insights query (select all `/aws/lambda/<prefix>-*` groups):
```
fields @timestamp, service, level, message, orderId, eventType, outcome, error
| filter level in ["ERROR","WARNING"] or orderId = "ord_…"
| sort @timestamp desc | limit 100
```

## Deployment

| Symptom | Cause | Fix |
|---|---|---|
| `ExpiredToken` / `InvalidClientTokenId` | Lab credentials expired, or the values in `~/.aws/credentials` are wrapped in quotes | Restart lab, re-copy credentials without quotes (deployment.md §2) |
| `s3:GetBucketObjectLockConfiguration ... explicit deny in a service control policy` | `aws_s3_bucket` was used for the frontend bucket; the Academy SCP blocks that read | The bucket is created by `terraform_data.frontend_bucket` (AWS CLI) instead — keep it that way |
| `AccessDenied ... iam:CreateRole` | `use_lab_role = false` in the Academy | Set `use_lab_role = true` |
| `Error: reading IAM Role (LabRole)` | Not an Academy account | Set `use_lab_role = false` |
| Region errors / service not available | Lab region restriction | Use `us-east-1` (or `us-west-2`) |
| `ResourceConflictException` for event source mapping/function concurrency | Lab account concurrency limit | Keep `worker_max_concurrency = 2`; don't add reserved concurrency |
| KMS `AccessDenied` when publishing to SNS (orders stay `PENDING`, logs show `SNS publish failed`) | Lab blocks the AWS-managed SNS key | `enable_sns_encryption = false`, `terraform apply`; the outbox publisher then publishes the stuck events |
| CloudFront errors in the lab | CloudFront not allowed | Keep `enable_cloudfront = false` |
| Frontend shows "Can't reach the server" | Wrong `VITE_API_BASE_URL` or CORS | Re-run `scripts/deploy-frontend.sh`; check `cors_allowed_origins` contains your local origin |
| Browser CORS error only for localhost:5173 | Origin not in the list | Add it to `cors_allowed_origins`, apply |

## Runtime

| Symptom | Where to look | Fix |
|---|---|---|
| Order stays **PENDING** | Orders item: `outboxStatus` present? `stock` logs | If `outboxStatus = PENDING_PUBLISH` the outbox Lambda will retry every minute — check its logs. Otherwise check the stock DLQ, then Admin › Retry. |
| Order stays **PROCESSING** | `payment` logs, payment DLQ | Transient failure → message reaches the DLQ after 3 receives (≈ 6 min). Fix the cause, then Admin › Retry (preferred) or redrive. |
| Status changed but no notification | `notify` logs / notify DLQ | Admin › Retry offers `RENOTIFY` after 120 s |
| `401` on every call after ~1 h | Access token expired and no refresh token in this tab | Sign in again (by design the refresh token lives in memory only) |
| `403` on admin pages | User's `role` is not `admin` | `scripts/create-admin.sh <email> <password>`, sign out and in again |
| `403 {"message":"Forbidden"}` on every protected call | Lambda Authorizer rejected the token (expired, or `jwt_secret` was rotated by a re-create) | Sign in again; check the `<prefix>-authorizer` Lambda logs |
| DLQ alarm email never arrives | Subscription not confirmed | Click the SNS confirmation link; check `aws sns list-subscriptions-by-topic` |
| Admin › Queues shows "Could not read queue attributes" | Missing `QUEUES_JSON` or permissions | Check the admin Lambda env / role |
| Redrive returns `REDRIVE_FAILED` | A move task is running or the role lacks `sqs:StartMessageMoveTask` | Use the SQS console "Start DLQ redrive", or retry the orders individually |

## Inspecting and recovering DLQ messages

```bash
DLQ=$(terraform -chdir=terraform output -json queue_urls | python3 -c 'import json,sys;print(json.load(sys.stdin)["payment"]["dlq"])')
aws sqs receive-message --queue-url "$DLQ" --max-number-of-messages 10 --visibility-timeout 5 \
  --message-attribute-names All --attribute-names All
```
Each body is an order event (`orderId`, `eventType`, `attempt`). Messages parked by a worker as *permanent*
failures carry an `errorReason` attribute.

Safe recovery order:
1. Read the logs for the `orderId` and fix the cause (data, configuration, permissions).
2. **Retry the order** from the admin UI. This starts a new attempt; the old DLQ message becomes stale.
3. Then redrive or purge the DLQ. Redriving stale messages is harmless (they are ignored); messages with
   `errorReason` will fail again — delete them after investigation
   (`aws sqs purge-queue --queue-url "$DLQ"`).

Never edit order status by hand in DynamoDB unless you also fix `inventory.reserved` — the payment step relies on
the reservation recorded there.

## Local development

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: order_system` when running tests | Run from `backend/` (pytest config adds `src`, `local`, `tests` to the path) |
| Frontend can't call the local API | Use `http://localhost:5173` (allowed origin) and `VITE_API_BASE_URL=http://127.0.0.1:8000` |
| Local data disappeared | The dev server is in-memory; restarting resets it and re-seeds products/accounts |
