"""Keeps code and infrastructure in sync: API routes and DynamoDB key schemas
used by the backend must match what Terraform deploys."""

from __future__ import annotations

import re
from pathlib import Path

from order_system.repositories.tables import LAYOUTS
from order_system_local.routes import ROUTES

TF = Path(__file__).resolve().parents[2] / "terraform"


def test_api_routes_match_terraform():
    text = (TF / "api_gateway.tf").read_text()
    tf_routes = dict(re.findall(r'"((?:GET|POST|PATCH|PUT|DELETE) [^"]+)"\s*=\s*\{[^}]*auth\s*=\s*(true|false)', text))
    local_routes = {key: ("true" if auth else "false") for key, _, auth in ROUTES}
    assert local_routes == tf_routes


def _table_block(text: str, resource: str) -> str:
    start = text.index(f'resource "aws_dynamodb_table" "{resource}"')
    depth, i = 0, text.index("{", start)
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[i:j]
    raise AssertionError("unbalanced")


def test_dynamodb_key_schema_matches_terraform():
    text = (TF / "dynamodb.tf").read_text()
    for logical, layout in LAYOUTS.items():
        block = _table_block(text, logical)
        assert re.search(rf'hash_key\s*=\s*"{layout.partition_key}"', block), logical
        if layout.sort_key:
            assert re.search(rf'range_key\s*=\s*"{layout.sort_key}"', block.split("global_secondary_index")[0]), logical
        gsis = re.findall(
            r'global_secondary_index\s*\{\s*name\s*=\s*"([^"]+)"\s*hash_key\s*=\s*"([^"]+)"\s*range_key\s*=\s*"([^"]+)"',
            block,
        )
        assert {n: (h, r) for n, h, r in gsis} == dict(layout.indexes.items()), logical
        if layout.ttl_attribute:
            assert f'attribute_name = "{layout.ttl_attribute}"' in block


def test_worker_handlers_exist_for_terraform_functions():
    import importlib

    text = (TF / "lambda.tf").read_text()
    for handler in re.findall(r'handler\s*=\s*"(order_system\.[^"]+)"', text):
        module, func = handler.rsplit(".", 1)
        assert callable(getattr(importlib.import_module(module), func)), handler


def test_openapi_documents_every_route():
    yaml = __import__("pytest").importorskip("yaml")
    spec = yaml.safe_load((Path(__file__).resolve().parents[1] / "openapi.yaml").read_text())
    documented = {f"{m.upper()} {p}" for p, ops in spec["paths"].items() for m in ops}
    assert documented == {key for key, _, _ in ROUTES}
    for key, _, auth in ROUTES:
        method, path = key.split(" ", 1)
        assert bool(spec["paths"][path][method.lower()].get("security")) == auth, key
