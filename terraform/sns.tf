# ---------------------------------------------------------------------------
# Order events topic ("OrderPlaced SNS topic" in the diagram).
# Carries every order lifecycle event; each queue subscribes with a filter
# policy on the eventType message attribute and raw message delivery.
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "order_events" {
  name              = "${local.name_prefix}-order-events"
  kms_master_key_id = var.enable_sns_encryption ? "alias/aws/sns" : null
}

resource "aws_sns_topic_policy" "order_events" {
  arn = aws_sns_topic.order_events.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "OwnerAccountOnly"
        Effect    = "Allow"
        Principal = { AWS = "arn:${local.partition}:iam::${local.account_id}:root" }
        Action    = ["sns:Publish", "sns:Subscribe", "sns:GetTopicAttributes", "sns:ListSubscriptionsByTopic"]
        Resource  = aws_sns_topic.order_events.arn
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.order_events.arn
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
}

resource "aws_sns_topic_subscription" "service_queues" {
  for_each = local.services

  topic_arn            = aws_sns_topic.order_events.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.work[each.key].arn
  raw_message_delivery = true
  filter_policy_scope  = "MessageAttributes"
  filter_policy        = jsonencode({ eventType = each.value.event_types })

  depends_on = [aws_sqs_queue_policy.work]
}

# ---------------------------------------------------------------------------
# Customer email topic ("Customer email SNS" in the diagram). Optional: each
# customer's email subscription is created at registration with a filter
# policy on customerId and must be confirmed by the customer.
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "customer_email" {
  count             = var.enable_customer_email ? 1 : 0
  name              = "${local.name_prefix}-customer-email"
  kms_master_key_id = var.enable_sns_encryption ? "alias/aws/sns" : null
}
