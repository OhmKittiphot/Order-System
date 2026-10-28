# One work queue + one DLQ per service (stock, payment, notify).
# SSE-SQS encryption (SQS-managed keys) works with SNS delivery without a
# customer managed KMS key.

resource "aws_sqs_queue" "dlq" {
  for_each = local.services

  name                      = "${local.name_prefix}-${each.key}-dlq"
  message_retention_seconds = 1209600 # 14 days: time to investigate
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "work" {
  for_each = local.services

  name                       = "${local.name_prefix}-${each.key}-queue"
  visibility_timeout_seconds = local.queue_visibility_timeout
  message_retention_seconds  = 345600 # 4 days
  receive_wait_time_seconds  = 20     # long polling
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = var.max_receive_count
  })
}

# Only the matching work queue may use a DLQ as its dead-letter target.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  for_each = local.services

  queue_url = aws_sqs_queue.dlq[each.key].id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.work[each.key].arn]
  })
}

# Only the order-events topic may send to the work queues.
resource "aws_sqs_queue_policy" "work" {
  for_each = local.services

  queue_url = aws_sqs_queue.work[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowOrderEventsTopic"
        Effect    = "Allow"
        Principal = { Service = "sns.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.work[each.key].arn
        Condition = { ArnEquals = { "aws:SourceArn" = aws_sns_topic.order_events.arn } }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "sqs:*"
        Resource  = aws_sqs_queue.work[each.key].arn
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
}
