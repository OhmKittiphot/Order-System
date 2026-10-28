# Deployment Guide (AWS Academy Learner Lab)

## 1. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Terraform | 1.6 – 1.x | `terraform -version` |
| AWS CLI | v2 | `aws --version` |
| Python | 3.12+ (with `pip install boto3` for the seed script) | `python3 --version` |
| Node.js | 20+ / npm | `node --version` |

## 2. AWS Academy credentials

1. Open the Learner Lab, click **Start Lab**, wait for the dot to turn green.
2. Click **AWS Details › AWS CLI: Show** and copy the block.
3. Paste it into `~/.aws/credentials` (it replaces the `[default]` profile):
   ```ini
   [default]
   aws_access_key_id=ASIA...
   aws_secret_access_key=...
   aws_session_token=...
   ```
   Never put these values in the repository, `terraform.tfvars` or the frontend. They expire when the lab
   session ends (about 4 h) — repeat this step after every restart.
4. Set the region: `aws configure set region us-east-1`.
5. Verify:
   ```bash
   aws sts get-caller-identity        # Arn should contain assumed-role/voclabs/...
   aws configure get region           # us-east-1
   scripts/check-aws.sh               # tools, identity, region and read-only probes of every service used
   ```
   If `get-caller-identity` fails, the session is stopped or the credentials expired.

## 3. Configure

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```
Edit at least `admin_alert_email` (you will receive an SNS subscription confirmation email — click it, or
alerts won't arrive). Keep `use_lab_role = true` in the Academy.

## 4. Deploy (one command)

```bash
scripts/deploy.sh
```
This runs `check-aws.sh`, `terraform init/fmt/validate/plan/apply`, seeds the 8 sample products and builds
and uploads the frontend. Step by step instead:

```bash
cd terraform
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
cd ..
python3 scripts/seed_products.py
scripts/deploy-frontend.sh
scripts/create-admin.sh admin@example.com 'ChangeMe123'
terraform -chdir=terraform output frontend_url
```

Terraform creates resources in dependency order: tables, topics, queues and the JWT signing key first; the Lambda
functions (whose environment variables reference them) next; then the SQS event source mappings and API
routes; the frontend bucket last (its URL is added to the API CORS list).

### Remote state (optional)
Local state (`terraform/terraform.tfstate`) is the default. To use S3, create a bucket once
(`aws s3 mb s3://<unique>-tfstate`), uncomment `backend "s3" {}` in `versions.tf`, and run
`terraform init -backend-config="bucket=<unique>-tfstate" -backend-config="key=ordersys/dev.tfstate" -backend-config="region=us-east-1" -migrate-state`.
Do not commit state files: they contain resource ids and configuration.

## 5. Verify the deployment

```bash
API=$(terraform -chdir=terraform output -raw api_url)
curl -s $API/products | head -c 300                                   # 200 + products
curl -s -o /dev/null -w '%{http_code}\n' $API/orders                   # 401 (JWT required)
python3 scripts/e2e_test.py --allow-mutations \
  --admin-email admin@example.com --admin-password 'ChangeMe123'      # ~1 min
python3 scripts/e2e_test.py --allow-mutations --include-dlq \
  --admin-email admin@example.com --admin-password 'ChangeMe123'      # + DLQ scenario, ~8-10 min
```

AWS-side checks:
```bash
aws dynamodb scan --table-name "$(terraform -chdir=terraform output -json table_names | python3 -c 'import json,sys;print(json.load(sys.stdin)["orders"])')" --max-items 3
aws sqs get-queue-attributes --queue-url <payment dlq url from `terraform output queue_urls`> --attribute-names ApproximateNumberOfMessages
aws cloudwatch describe-alarms --alarm-name-prefix "$(terraform -chdir=terraform output -raw alarm_name_prefix)" \
  --query 'MetricAlarms[].[AlarmName,StateValue]' --output table
aws logs tail /aws/lambda/$(terraform -chdir=terraform output -raw name_prefix)-stock --since 15m
```

## 6. Demo script (manual)

1. Shop → add earbuds → Cart → Place order → watch Received → Stock → Payment → Notified.
2. Order the **Limited Edition Mug** twice (two accounts) → one is confirmed, the other fails with "Insufficient stock".
3. Order **TEST - Declined Payment Item** → fails at Payment; Admin › Products shows its stock unchanged.
4. Order **TEST - Flaky Payment Item** → stays in Processing; after ~6 min (3 × 120 s visibility timeout) the
   payment DLQ has a message, the `…payment-dlq-not-empty` alarm fires and the admin email arrives.
   Admin › Failed orders → open the order → **Retry order** → Confirmed.
5. Admin › Products & stock → restock the mug → retry the out-of-stock order → Confirmed.

## 7. Deployment checklist

- [ ] Lab session started; `aws sts get-caller-identity` works; region is `us-east-1`
- [ ] `scripts/check-aws.sh` passes
- [ ] `terraform/terraform.tfvars` created; `admin_alert_email` set; `use_lab_role = true`
- [ ] `terraform validate` and `terraform plan` reviewed (≈ 105–110 resources to add on first apply with the default settings)
- [ ] `terraform apply` succeeded; outputs `api_url` and `frontend_url` present
- [ ] SNS subscription confirmation email clicked
- [ ] `python3 scripts/seed_products.py` reports 8 products
- [ ] `scripts/deploy-frontend.sh` uploaded the build; the frontend URL loads
- [ ] Admin user created with `scripts/create-admin.sh`
- [ ] `scripts/e2e_test.py --allow-mutations …` passes
- [ ] No credentials, `terraform.tfstate` or `.env*` files staged in git (`git status`)

## 8. Cleanup

```bash
scripts/destroy.sh          # terraform destroy + lists any leftovers with the stack prefix
```
Or `terraform -chdir=terraform destroy`. The S3 bucket is created with `force_destroy`, so uploaded files are
removed too. Users (in the Users table), other DynamoDB data and log groups are deleted with their resources.

### Cleanup checklist
- [ ] `terraform destroy` completed with "Destroy complete!"
- [ ] `scripts/destroy.sh` leftover listing is empty (tables, functions, queues, log groups)
- [ ] `aws cloudwatch describe-alarms --alarm-name-prefix <prefix>` returns nothing
- [ ] `aws s3 ls | grep <prefix>` returns nothing
- [ ] If you used remote state: delete the state bucket manually
- [ ] Remove `frontend/.env.production.local`; end the lab session

What keeps costing money if you don't destroy: DynamoDB PITR and storage, CloudWatch alarms (per alarm-month),
log storage, the scheduled outbox Lambda (1 invocation/min), S3 storage and CloudFront (if enabled). Stopping
the lab session does **not** stop these charges. See [cost-estimation.md](cost-estimation.md).
