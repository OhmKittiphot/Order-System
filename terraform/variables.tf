# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------
variable "aws_region" {
  description = "AWS region to deploy into (AWS Academy Learner Lab normally allows us-east-1 and us-west-2)."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short project name used in resource names (lowercase letters, digits, hyphens)."
  type        = string
  default     = "ordersys"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,15}$", var.project_name))
    error_message = "project_name must be 3-16 chars: lowercase letters, digits and hyphens."
  }
}

variable "environment" {
  description = "Environment name, e.g. dev or test."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z0-9]{2,8}$", var.environment))
    error_message = "environment must be 2-8 lowercase letters/digits."
  }
}

variable "extra_tags" {
  description = "Additional tags applied to every resource."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# IAM (AWS Academy cannot create IAM roles)
# ---------------------------------------------------------------------------
variable "use_lab_role" {
  description = "true = attach the pre-existing AWS Academy 'LabRole' to every Lambda (Learner Lab cannot create IAM roles). false = create one least-privilege role per Lambda (normal AWS accounts)."
  type        = bool
  default     = true
}

variable "lab_role_name" {
  description = "Name of the existing role used when use_lab_role = true."
  type        = string
  default     = "LabRole"
}

# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------
variable "lambda_runtime" {
  description = "Python runtime for all functions."
  type        = string
  default     = "python3.12"
}

variable "lambda_architecture" {
  description = "x86_64 or arm64 (arm64 is ~20% cheaper per GB-second)."
  type        = string
  default     = "x86_64"

  validation {
    condition     = contains(["x86_64", "arm64"], var.lambda_architecture)
    error_message = "lambda_architecture must be x86_64 or arm64."
  }
}

variable "lambda_memory_mb" {
  description = "Memory for each function."
  type        = number
  default     = 256
}

variable "worker_max_concurrency" {
  description = "Maximum concurrent Lambda invocations per SQS event source (min 2). Kept low because Learner Lab accounts have a small concurrency limit."
  type        = number
  default     = 2
}

variable "log_level" {
  description = "Application log level (DEBUG, INFO, WARNING, ERROR)."
  type        = string
  default     = "INFO"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for Lambda and API access logs."
  type        = number
  default     = 7
}

# ---------------------------------------------------------------------------
# Business configuration
# ---------------------------------------------------------------------------
variable "currency" {
  description = "ISO currency code for all prices (amounts are stored in minor units)."
  type        = string
  default     = "THB"
}

variable "low_stock_threshold" {
  description = "Products with available stock at or below this are reported as low stock."
  type        = number
  default     = 5
}

variable "payment_simulation_mode" {
  description = "deterministic = approve unless a test product says otherwise; random = decline payment_failure_rate of payments."
  type        = string
  default     = "deterministic"

  validation {
    condition     = contains(["deterministic", "random"], var.payment_simulation_mode)
    error_message = "payment_simulation_mode must be deterministic or random."
  }
}

variable "payment_failure_rate" {
  description = "Decline probability when payment_simulation_mode = random (0.0 - 1.0)."
  type        = number
  default     = 0.0
}

variable "enable_test_scenarios" {
  description = "Honour admin-configured product testBehavior flags (PAYMENT_DECLINE, PAYMENT_TRANSIENT_ONCE). Set false outside demos."
  type        = bool
  default     = true
}

variable "access_token_ttl_seconds" {
  description = "Lifetime of the access token issued by the Auth Lambda (refresh tokens last 1 day)."
  type        = number
  default     = 3600

  validation {
    condition     = var.access_token_ttl_seconds >= 300 && var.access_token_ttl_seconds <= 86400
    error_message = "access_token_ttl_seconds must be between 300 and 86400."
  }
}

variable "stuck_order_seconds" {
  description = "An order with no progress for this long is offered for admin retry."
  type        = number
  default     = 120
}

variable "retry_cooldown_seconds" {
  description = "Minimum time between two retries of the same order."
  type        = number
  default     = 30
}

variable "max_order_retries" {
  description = "Maximum admin retries per order."
  type        = number
  default     = 5
}

# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------
variable "max_receive_count" {
  description = "Receives before SQS moves a message to the DLQ."
  type        = number
  default     = 3
}

variable "enable_sns_encryption" {
  description = "Encrypt the order-events and customer-email topics with the AWS managed key alias/aws/sns. Set false if your lab blocks KMS."
  type        = bool
  default     = true
}

variable "outbox_schedule_expression" {
  description = "How often the outbox publisher looks for unpublished events."
  type        = string
  default     = "rate(1 minute)"
}

variable "enable_customer_email" {
  description = "Create the customer-email SNS topic. Each new customer gets an email subscription they must confirm. In-app notifications work either way."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------
variable "admin_alert_email" {
  description = "Email address subscribed to the dlq-alerts topic (confirm the subscription email). Empty = no subscription."
  type        = string
  default     = ""
}

variable "dlq_alarm_threshold" {
  description = "Alarm when a DLQ has more than this many visible messages."
  type        = number
  default     = 0
}

variable "lambda_error_alarm_threshold" {
  description = "Alarm when a function reports at least this many errors in 5 minutes."
  type        = number
  default     = 3
}

variable "queue_age_alarm_seconds" {
  description = "Alarm when the oldest message in a work queue is older than this."
  type        = number
  default     = 300
}

# ---------------------------------------------------------------------------
# API & frontend
# ---------------------------------------------------------------------------
variable "cors_allowed_origins" {
  description = "Extra origins allowed to call the API (the deployed frontend origin is added automatically). Keep localhost only for development."
  type        = list(string)
  default     = ["http://localhost:5173"]
}

variable "api_throttle_rate_limit" {
  description = "Steady-state requests per second allowed by the API stage."
  type        = number
  default     = 20
}

variable "api_throttle_burst_limit" {
  description = "Burst requests allowed by the API stage."
  type        = number
  default     = 40
}

variable "enable_cloudfront" {
  description = "Serve the frontend through CloudFront (HTTPS, private bucket). false = S3 static website endpoint (HTTP only), which matches the diagram and is the simplest option in the lab."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# Data protection
# ---------------------------------------------------------------------------
variable "enable_point_in_time_recovery" {
  description = "Enable DynamoDB PITR on the Orders, Inventory and Payments tables (small extra cost)."
  type        = bool
  default     = true
}
