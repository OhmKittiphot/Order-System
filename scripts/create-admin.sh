#!/usr/bin/env bash
# Create (or promote) an administrator directly in the Users table.
# Usage: scripts/create-admin.sh admin@example.com 'StrongPassw0rd'
# The password is hashed locally (same PBKDF2 code as the Auth Lambda) and
# only the hash is written to DynamoDB. Needs python3 + boto3 and lab credentials.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EMAIL="${1:?usage: create-admin.sh <email> <password>}"
PASSWORD="${2:?usage: create-admin.sh <email> <password>}"
USERS_TABLE="$(terraform -chdir="$ROOT/terraform" output -json table_names | python3 -c 'import json,sys;print(json.load(sys.stdin)["users"])')"
REGION="$(terraform -chdir="$ROOT/terraform" output -raw region)"

ADMIN_EMAIL="$EMAIL" ADMIN_PASSWORD="$PASSWORD" USERS_TABLE="$USERS_TABLE" AWS_DEFAULT_REGION="$REGION" \
  BACKEND_SRC="$ROOT/backend/src" python3 - <<'PY'
import os, sys, uuid
from datetime import datetime, timezone

sys.path.insert(0, os.environ["BACKEND_SRC"])
import boto3
from order_system.schemas.validation import validate_email, validate_password
from order_system.utils.security import hash_password

email = validate_email(os.environ["ADMIN_EMAIL"])
password_hash = hash_password(validate_password(os.environ["ADMIN_PASSWORD"]))
table = boto3.resource("dynamodb").Table(os.environ["USERS_TABLE"])
now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

credential = table.get_item(Key={"userId": "EMAIL#" + email}, ConsistentRead=True).get("Item")
if credential:
    user_id = credential["ownerId"]
    table.update_item(
        Key={"userId": "EMAIL#" + email},
        UpdateExpression="SET passwordHash = :h",
        ExpressionAttributeValues={":h": password_hash},
    )
    table.update_item(
        Key={"userId": user_id},
        UpdateExpression="SET #r = :admin, updatedAt = :now",
        ExpressionAttributeNames={"#r": "role"},
        ExpressionAttributeValues={":admin": "admin", ":now": now},
    )
    print(f"Promoted existing user to admin and reset the password: {email}")
else:
    user_id = str(uuid.uuid4())
    client = boto3.client("dynamodb")
    profile = {"userId": user_id, "entityType": "USER", "email": email, "displayName": "Administrator",
               "role": "admin", "createdAt": now, "updatedAt": now}
    cred = {"userId": "EMAIL#" + email, "entityType": "CREDENTIAL", "ownerId": user_id,
            "passwordHash": password_hash, "createdAt": now}
    client.transact_write_items(TransactItems=[
        {"Put": {"TableName": table.name, "Item": {k: {"S": v} for k, v in item.items()},
                 "ConditionExpression": "attribute_not_exists(userId)"}}
        for item in (profile, cred)
    ])
    print(f"Admin created: {email}")
PY
echo "Sign in through the web app with that email (role 'admin')."
