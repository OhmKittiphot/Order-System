# Cost Estimation

Deploying this project is **not free**. AWS Academy gives a budget (typically USD 50–100) that real charges are
deducted from, and charges continue while the lab session is stopped. The figures below are approximate
us-east-1 list prices — always check the official pricing pages and the lab's budget display.

## What is billed

| Service | Pricing model (approx.) | This project |
|---|---|---|
| API Gateway HTTP API | ~$1.00 per million requests | demo traffic: cents |
| Lambda | ~$0.20 per million requests + ~$0.0000167 per GB-second (x86) | 9 functions × 256 MB; demo: cents. Outbox schedule ≈ 43,800 invocations/month |
| DynamoDB on-demand | per million read/write request units + ~$0.25/GB-month storage | 7 tables, KB of data: cents |
| DynamoDB PITR | ~$0.20/GB-month | 3 tables, tiny: < $0.01 |
| SQS | ~$0.40 per million requests (Lambda long-polls continuously) | event source pollers make requests even when idle; typically well under $1/month |
| SNS | ~$0.50 per million publishes; email notifications ~$2 per 100,000 | cents |
| CloudWatch alarms | ~$0.10 per standard alarm per month | 16 alarms (3 DLQ + 3 queue-age + 9 Lambda + 1 API) ≈ **$1.60/month** — the largest fixed cost |
| CloudWatch Logs | ~$0.50/GB ingested + storage | 7-day retention; demo: cents |
| S3 | ~$0.023/GB-month + requests | < $0.01 |
| CloudFront (optional) | per GB out + requests | off by default |
| EventBridge scheduled rule | no charge for scheduled rules | $0 |
| KMS (AWS-managed SNS key) | no key fee; ~$0.03 per 10,000 requests | cents |

**Expected total for a few days of demos: well under USD 5**, dominated by alarms and idle SQS polling.

Not used on purpose: EC2, NAT Gateways, RDS/Aurora, provisioned DynamoDB capacity, ElastiCache —
the usual sources of large recurring lab bills.

## Billing risks

* **Forgetting to destroy.** Alarms, log storage, PITR, idle SQS polling and the outbox schedule keep billing.
  Run `scripts/destroy.sh` when done.
* **Load testing** multiplies Lambda, API Gateway, DynamoDB and SNS requests linearly.
* **`payment_simulation_mode = random`** with retries can generate DLQ traffic and alarm notifications.
* **Email notifications** (`enable_customer_email`) are billed per email.
* **Log level `DEBUG`** increases log ingestion.

## Reducing cost further

* `enable_point_in_time_recovery = false`
* `lambda_architecture = "arm64"` (≈ 20 % cheaper compute)
* `outbox_schedule_expression = "rate(5 minutes)"`
* Raise `lambda_error_alarm_threshold` or delete the per-function error alarms you don't need.

Sources to verify current prices: AWS pricing pages for API Gateway, Lambda, DynamoDB, SQS, SNS, CloudWatch,
S3, and the [AWS Pricing Calculator](https://calculator.aws/).
