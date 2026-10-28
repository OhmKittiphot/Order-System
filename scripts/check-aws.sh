#!/usr/bin/env bash
# Pre-deployment checks for AWS Academy Learner Lab (or any account).
# Verifies CLI credentials, the active identity, region and basic service access.
set -uo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || true)}}"
REGION="${REGION:-us-east-1}"
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$*"; FAILED=1; }
FAILED=0

echo "== Tools"
for tool in aws terraform python3 node npm; do
  if command -v "$tool" >/dev/null 2>&1; then ok "$tool: $($tool --version 2>&1 | head -1)"; else fail "$tool not found"; fi
done

echo "== Credentials and lab session"
if IDENTITY=$(aws sts get-caller-identity --output json 2>&1); then
  ok "Authenticated as $(echo "$IDENTITY" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["Arn"])')"
  echo "$IDENTITY" | grep -q "assumed-role/voclabs" && ok "Looks like an AWS Academy Learner Lab session"
else
  fail "aws sts get-caller-identity failed - the lab session is stopped or the credentials expired."
  echo "     Start the lab, open 'AWS Details' > 'AWS CLI', and paste the block into ~/.aws/credentials."
  exit 1
fi

echo "== Region"
ok "Using region $REGION (override with AWS_REGION=...)"
[[ "$REGION" == "us-east-1" || "$REGION" == "us-west-2" ]] || warn "Learner Lab usually only allows us-east-1 and us-west-2"

echo "== Service access (read-only probes)"
probe() { local name="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$name"; else fail "$name ($*)"; fi; }
probe "DynamoDB"   aws dynamodb list-tables --region "$REGION" --max-items 1
probe "Lambda"     aws lambda list-functions --region "$REGION" --max-items 1
probe "SQS"        aws sqs list-queues --region "$REGION" --max-results 1
probe "SNS"        aws sns list-topics --region "$REGION"
probe "API GW v2"  aws apigatewayv2 get-apis --region "$REGION" --max-results 1
probe "CloudWatch" aws cloudwatch describe-alarms --region "$REGION" --max-records 1
probe "S3"         aws s3api list-buckets
if aws iam get-role --role-name LabRole >/dev/null 2>&1; then
  ok "LabRole exists (keep use_lab_role = true)"
else
  warn "LabRole not found - outside the Academy set use_lab_role = false in terraform.tfvars"
fi

echo
if [[ $FAILED -eq 0 ]]; then echo "All checks passed."; else echo "Some checks failed - fix them before deploying."; exit 1; fi
