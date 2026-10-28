# One deployment package (backend/src, standard library + boto3 from the
# runtime) shared by all functions; each function has its own handler.

# HS256 signing key for access/refresh tokens. Stored in Terraform state and
# in the two functions' (KMS-encrypted) environment; `terraform apply
# -replace=random_password.jwt_secret` rotates it and signs everyone out.
resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

data "archive_file" "backend" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/src"
  output_path = "${path.module}/build/backend.zip"
  excludes    = ["order_system/__pycache__", "order_system/handlers/__pycache__", "order_system/services/__pycache__", "order_system/repositories/__pycache__", "order_system/models/__pycache__", "order_system/schemas/__pycache__", "order_system/utils/__pycache__", "order_system/config/__pycache__"]
}

locals {
  functions = {
    auth = {
      handler     = "order_system.handlers.api_auth.handler"
      timeout     = 10
      description = "Auth Lambda: register/login, issues JWTs, user profile"
    }
    authorizer = {
      handler     = "order_system.handlers.authorizer.handler"
      timeout     = 5
      description = "Lambda Authorizer: verifies the JWT on protected API routes"
    }
    products = {
      handler     = "order_system.handlers.api_products.handler"
      timeout     = 10
      description = "Public product catalog API"
    }
    orders = {
      handler     = "order_system.handlers.api_orders.handler"
      timeout     = 10
      description = "Order Lambda: create order, order status/history, notifications"
    }
    admin = {
      handler     = "order_system.handlers.api_admin.handler"
      timeout     = 15
      description = "Admin API: orders, retry, products, stock, DLQ status"
    }
    stock = {
      handler     = "order_system.handlers.workers.stock_handler"
      timeout     = local.worker_timeout_seconds
      description = "Stock Lambda: atomic inventory reservation"
    }
    payment = {
      handler     = "order_system.handlers.workers.payment_handler"
      timeout     = local.worker_timeout_seconds
      description = "Payment Lambda: simulated payment, commit/release stock"
    }
    notify = {
      handler     = "order_system.handlers.workers.notify_handler"
      timeout     = local.worker_timeout_seconds
      description = "Notify Lambda: customer notifications"
    }
    outbox = {
      handler     = "order_system.handlers.workers.outbox_handler"
      timeout     = 30
      description = "Outbox publisher: re-publishes events that failed to publish"
    }
  }

  queues_json = jsonencode({
    for k, _ in local.services : k => {
      queueUrl = aws_sqs_queue.work[k].url
      queueArn = aws_sqs_queue.work[k].arn
      dlqUrl   = aws_sqs_queue.dlq[k].url
      dlqArn   = aws_sqs_queue.dlq[k].arn
    }
  })

  # Non-secret configuration only. AWS credentials come from the execution role.
  common_environment = {
    SERVICE_NAME             = var.project_name
    ENVIRONMENT              = var.environment
    LOG_LEVEL                = var.log_level
    ORDERS_TABLE             = aws_dynamodb_table.orders.name
    PRODUCTS_TABLE           = aws_dynamodb_table.products.name
    INVENTORY_TABLE          = aws_dynamodb_table.inventory.name
    PAYMENTS_TABLE           = aws_dynamodb_table.payments.name
    NOTIFICATIONS_TABLE      = aws_dynamodb_table.notifications.name
    USERS_TABLE              = aws_dynamodb_table.users.name
    IDEMPOTENCY_TABLE        = aws_dynamodb_table.idempotency.name
    ORDER_EVENTS_TOPIC_ARN   = aws_sns_topic.order_events.arn
    CUSTOMER_EMAIL_TOPIC_ARN = var.enable_customer_email ? aws_sns_topic.customer_email[0].arn : ""
    CUSTOMER_EMAIL_ENABLED   = tostring(var.enable_customer_email)
    CURRENCY                 = var.currency
    LOW_STOCK_THRESHOLD      = tostring(var.low_stock_threshold)
    PAYMENT_SIMULATION_MODE  = var.payment_simulation_mode
    PAYMENT_FAILURE_RATE     = tostring(var.payment_failure_rate)
    ENABLE_TEST_SCENARIOS    = tostring(var.enable_test_scenarios)
    STUCK_ORDER_SECONDS      = tostring(var.stuck_order_seconds)
    RETRY_COOLDOWN_SECONDS   = tostring(var.retry_cooldown_seconds)
    MAX_RETRIES              = tostring(var.max_order_retries)
    QUEUES_JSON              = local.queues_json
    ALARM_NAME_PREFIX        = local.alarm_prefix
  }

  # The JWT signing key goes only to the two functions that need it.
  jwt_functions = {
    auth       = { JWT_SECRET = random_password.jwt_secret.result, ACCESS_TOKEN_TTL_SECONDS = tostring(var.access_token_ttl_seconds) }
    authorizer = { JWT_SECRET = random_password.jwt_secret.result }
  }

  worker_dlq = {
    stock   = aws_sqs_queue.dlq["stock"].url
    payment = aws_sqs_queue.dlq["payment"].url
    notify  = aws_sqs_queue.dlq["notify"].url
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.functions

  name              = "/aws/lambda/${local.name_prefix}-${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "fn" {
  for_each = local.functions

  function_name    = "${local.name_prefix}-${each.key}"
  description      = each.value.description
  role             = local.lambda_role_arns[each.key]
  runtime          = var.lambda_runtime
  architectures    = [var.lambda_architecture]
  handler          = each.value.handler
  filename         = data.archive_file.backend.output_path
  source_code_hash = data.archive_file.backend.output_base64sha256
  timeout          = each.value.timeout
  memory_size      = var.lambda_memory_mb

  environment {
    variables = merge(
      local.common_environment,
      contains(keys(local.worker_dlq), each.key) ? { OWN_DLQ_URL = local.worker_dlq[each.key] } : {},
      lookup(local.jwt_functions, each.key, {}),
    )
  }

  # The log group (same name Lambda would use) is created first so Terraform
  # owns its retention setting and deletes it on destroy.
  depends_on = [aws_cloudwatch_log_group.lambda]
}

# SQS -> Lambda with partial batch failure reporting.
resource "aws_lambda_event_source_mapping" "workers" {
  for_each = local.services

  event_source_arn                   = aws_sqs_queue.work[each.key].arn
  function_name                      = aws_lambda_function.fn[each.value.function].arn
  batch_size                         = 5
  maximum_batching_window_in_seconds = 1
  function_response_types            = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.worker_max_concurrency
  }
}

# Scheduled outbox publisher.
resource "aws_cloudwatch_event_rule" "outbox" {
  name                = "${local.name_prefix}-outbox-schedule"
  description         = "Re-publish order events whose publish step failed"
  schedule_expression = var.outbox_schedule_expression
}

resource "aws_cloudwatch_event_target" "outbox" {
  rule      = aws_cloudwatch_event_rule.outbox.name
  target_id = "outbox-publisher"
  arn       = aws_lambda_function.fn["outbox"].arn
}

resource "aws_lambda_permission" "outbox_schedule" {
  statement_id  = "AllowEventBridgeSchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn["outbox"].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.outbox.arn
}
