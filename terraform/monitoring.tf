# Operational alerting: DLQ alarm -> dlq-alerts SNS topic -> admin email.
# Kept separate from customer notifications.
#
# The alerts topic is not KMS-encrypted on purpose: CloudWatch alarms cannot
# publish to topics encrypted with the AWS managed key (a customer managed
# key with a custom policy would be needed, which the lab may not allow).
# Alert messages contain only alarm metadata, no customer data.

resource "aws_sns_topic" "alerts" {
  name = "${local.name_prefix}-dlq-alerts"
}

resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudWatchAlarms"
        Effect    = "Allow"
        Principal = { Service = "cloudwatch.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alerts.arn
        Condition = {
          StringEquals = { "aws:SourceAccount" = local.account_id }
          ArnLike      = { "aws:SourceArn" = "arn:${local.partition}:cloudwatch:${local.region}:${local.account_id}:alarm:${local.alarm_prefix}*" }
        }
      },
      {
        Sid       = "OwnerAccount"
        Effect    = "Allow"
        Principal = { AWS = "arn:${local.partition}:iam::${local.account_id}:root" }
        Action    = ["sns:Publish", "sns:Subscribe", "sns:GetTopicAttributes", "sns:ListSubscriptionsByTopic"]
        Resource  = aws_sns_topic.alerts.arn
      }
    ]
  })
}

resource "aws_sns_topic_subscription" "admin_email" {
  count     = var.admin_alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.admin_alert_email
}

# A message in any DLQ means processing failed max_receive_count times
# (or a worker parked a permanently invalid message).
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  for_each = local.services

  alarm_name        = "${local.alarm_prefix}${each.key}-dlq-not-empty"
  alarm_description = <<-EOT
    Service: ${each.key}. DLQ ${aws_sqs_queue.dlq[each.key].name} has messages that failed ${var.max_receive_count} times or were rejected as invalid.
    Troubleshoot: 1) CloudWatch Logs /aws/lambda/${local.name_prefix}-${each.value.function} (filter level = ERROR / WARNING)
    2) Admin UI > Operations shows stuck orders and DLQ counts 3) fix the cause, then Admin > Retry order or redrive the DLQ.
    See docs/troubleshooting.md.
  EOT

  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq[each.key].name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = var.dlq_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# Work piling up (consumer failing or throttled).
resource "aws_cloudwatch_metric_alarm" "queue_age" {
  for_each = local.services

  alarm_name          = "${local.alarm_prefix}${each.key}-queue-oldest-message-age"
  alarm_description   = "Service: ${each.key}. Oldest message in ${aws_sqs_queue.work[each.key].name} is older than ${var.queue_age_alarm_seconds}s. Check the ${each.key} Lambda logs, throttles and errors."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = aws_sqs_queue.work[each.key].name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  threshold           = var.queue_age_alarm_seconds
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.functions

  alarm_name          = "${local.alarm_prefix}${each.key}-lambda-errors"
  alarm_description   = "Function ${aws_lambda_function.fn[each.key].function_name} reported >= ${var.lambda_error_alarm_threshold} errors in 5 minutes. Check its CloudWatch log group."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.fn[each.key].function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.lambda_error_alarm_threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.alarm_prefix}api-5xx"
  alarm_description   = "HTTP API returned 5xx responses. Check the API access log group and the Lambda logs (search by correlationId)."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  dimensions          = { ApiId = aws_apigatewayv2_api.http.id }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
