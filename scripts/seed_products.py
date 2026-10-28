#!/usr/bin/env python3
"""Seed the deployed Products and Inventory tables from backend/seed/products.json.

Idempotent: products that already exist are left untouched (conditional put).
Requires boto3 and working AWS credentials; table names come from
`terraform output`.

    python3 scripts/seed_products.py [--region us-east-1]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tf_outputs() -> dict:
    raw = subprocess.check_output(["terraform", f"-chdir={ROOT / 'terraform'}", "output", "-json"])
    return {k: v["value"] for k, v in json.loads(raw).items()}


def main() -> int:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print("boto3 is required: pip install boto3", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser()
    parser.add_argument("--region")
    parser.add_argument("--currency", default="THB")
    args = parser.parse_args()

    out = tf_outputs()
    region = args.region or out["region"]
    tables = out["table_names"]
    ddb = boto3.resource("dynamodb", region_name=region)
    products = ddb.Table(tables["products"])
    inventory = ddb.Table(tables["inventory"])
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    created = skipped = 0
    for p in json.loads((ROOT / "backend" / "seed" / "products.json").read_text()):
        item = {
            "productId": p["seedId"],
            "name": p["name"],
            "description": p["description"],
            "priceMinor": p["priceMinor"],
            "currency": args.currency,
            "category": p["category"],
            "active": True,
            "catalogStatus": "ACTIVE",
            "createdAt": now,
            "updatedAt": now,
            "version": 1,
        }
        if p.get("testBehavior"):
            item["testBehavior"] = p["testBehavior"]
        try:
            products.put_item(Item=item, ConditionExpression="attribute_not_exists(productId)")
            inventory.put_item(
                Item={"productId": p["seedId"], "available": p["initialStock"], "reserved": 0, "sold": 0,
                      "version": 1, "updatedAt": now},
                ConditionExpression="attribute_not_exists(productId)",
            )
            created += 1
            print(f"  + {p['name']} (stock {p['initialStock']})")
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            skipped += 1
            print(f"  = {p['name']} already exists")
    print(f"Seed complete: {created} created, {skipped} already present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
