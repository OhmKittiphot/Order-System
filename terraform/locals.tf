resource "random_id" "suffix" {
  byte_length = 2
}

locals {
  name_prefix = "${var.project_name}-${var.environment}-${random_id.suffix.hex}"
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_region.current.name
  partition   = data.aws_partition.current.partition

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Application = "order-management-system"
    },
    var.extra_tags,
  )

  # The three asynchronous services from the architecture diagram.
  # event_types = the SNS filter policy for that service's queue.
  services = {
    stock = {
      event_types = ["OrderPlaced"]
      function    = "stock"
    }
    payment = {
      event_types = ["InventoryReserved"]
      function    = "payment"
    }
    notify = {
      event_types = ["OrderConfirmed", "OrderFailed"]
      function    = "notify"
    }
  }

  worker_timeout_seconds = 20
  # AWS recommends a visibility timeout of at least 6x the function timeout
  # for SQS event sources so a retried batch is not delivered twice in parallel.
  queue_visibility_timeout = local.worker_timeout_seconds * 6

  table_names = {
    orders        = "${local.name_prefix}-orders"
    products      = "${local.name_prefix}-products"
    inventory     = "${local.name_prefix}-inventory"
    payments      = "${local.name_prefix}-payments"
    notifications = "${local.name_prefix}-notifications"
    users         = "${local.name_prefix}-users"
    idempotency   = "${local.name_prefix}-idempotency"
  }

  alarm_prefix = "${local.name_prefix}-"
}
