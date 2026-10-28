#!/usr/bin/env bash
# Remove everything this project created. Run before your lab budget runs out.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/terraform"
PREFIX="$(terraform output -raw name_prefix 2>/dev/null || true)"
REGION="$(terraform output -raw region 2>/dev/null || echo "${AWS_REGION:-us-east-1}")"

terraform destroy -input=false "$@"

if [[ -n "$PREFIX" ]]; then
  echo "== Checking for leftovers named $PREFIX*"
  aws dynamodb list-tables --region "$REGION" --query "TableNames[?starts_with(@, '$PREFIX')]" --output text
  aws lambda list-functions --region "$REGION" --query "Functions[?starts_with(FunctionName, '$PREFIX')].FunctionName" --output text
  aws sqs list-queues --region "$REGION" --queue-name-prefix "$PREFIX" --output text || true
  aws logs describe-log-groups --region "$REGION" --log-group-name-prefix "/aws/lambda/$PREFIX" \
    --query "logGroups[].logGroupName" --output text
  echo "(empty output above = nothing left)"
fi
rm -f "$ROOT/frontend/.env.production.local"
