# All tables: on-demand billing (no idle cost for throughput), encrypted at
# rest with the AWS owned key (DynamoDB default, no KMS charge).
# Key layout must match backend/src/order_system/repositories/tables.py
# (checked by backend/tests/test_consistency.py).

resource "aws_dynamodb_table" "orders" {
  name         = local.table_names.orders
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "orderId"

  attribute {
    name = "orderId"
    type = "S"
  }
  attribute {
    name = "customerId"
    type = "S"
  }
  attribute {
    name = "createdAt"
    type = "S"
  }
  attribute {
    name = "entityType"
    type = "S"
  }
  attribute {
    name = "status"
    type = "S"
  }
  attribute {
    name = "outboxStatus"
    type = "S"
  }

  # Customer order history, newest first.
  global_secondary_index {
    name            = "customer-index"
    hash_key        = "customerId"
    range_key       = "createdAt"
    projection_type = "ALL"
  }

  # Admin "all orders" list, newest first (single partition is fine at lab scale).
  global_secondary_index {
    name            = "entity-index"
    hash_key        = "entityType"
    range_key       = "createdAt"
    projection_type = "ALL"
  }

  # Admin status filter and dashboard counts.
  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    range_key       = "createdAt"
    projection_type = "ALL"
  }

  # Sparse index: only orders with an unpublished event (transactional outbox).
  global_secondary_index {
    name            = "outbox-index"
    hash_key        = "outboxStatus"
    range_key       = "createdAt"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  deletion_protection_enabled = false
}

resource "aws_dynamodb_table" "products" {
  name         = local.table_names.products
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "productId"

  attribute {
    name = "productId"
    type = "S"
  }
  attribute {
    name = "catalogStatus"
    type = "S"
  }
  attribute {
    name = "name"
    type = "S"
  }

  # Public catalog: active products sorted by name (no table scans).
  global_secondary_index {
    name            = "catalog-index"
    hash_key        = "catalogStatus"
    range_key       = "name"
    projection_type = "ALL"
  }
}

resource "aws_dynamodb_table" "inventory" {
  name         = local.table_names.inventory
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "productId"

  attribute {
    name = "productId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }
}

resource "aws_dynamodb_table" "payments" {
  name         = local.table_names.payments
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "orderId"
  range_key    = "attempt"

  attribute {
    name = "orderId"
    type = "S"
  }
  attribute {
    name = "attempt"
    type = "N"
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }
}

resource "aws_dynamodb_table" "notifications" {
  name         = local.table_names.notifications
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "notificationId"

  attribute {
    name = "notificationId"
    type = "S"
  }
  attribute {
    name = "customerId"
    type = "S"
  }
  attribute {
    name = "createdAt"
    type = "S"
  }

  global_secondary_index {
    name            = "customer-index"
    hash_key        = "customerId"
    range_key       = "createdAt"
    projection_type = "ALL"
  }
}

resource "aws_dynamodb_table" "users" {
  name         = local.table_names.users
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"

  attribute {
    name = "userId"
    type = "S"
  }
}

resource "aws_dynamodb_table" "idempotency" {
  name         = local.table_names.idempotency
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "idempotencyId"

  attribute {
    name = "idempotencyId"
    type = "S"
  }

  # Records expire automatically (IDEMPOTENCY_TTL_HOURS, default 24h).
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
}

locals {
  tables = {
    orders        = aws_dynamodb_table.orders
    products      = aws_dynamodb_table.products
    inventory     = aws_dynamodb_table.inventory
    payments      = aws_dynamodb_table.payments
    notifications = aws_dynamodb_table.notifications
    users         = aws_dynamodb_table.users
    idempotency   = aws_dynamodb_table.idempotency
  }
}
