output "name_prefix" {
  description = "Prefix used for every resource name."
  value       = local.name_prefix
}

output "region" {
  description = "Deployment region."
  value       = local.region
}

output "api_url" {
  description = "Base URL of the HTTP API (use as VITE_API_BASE_URL)."
  value       = trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")
}

output "frontend_url" {
  description = "URL of the deployed frontend."
  value       = local.frontend_origin
}

output "frontend_bucket" {
  description = "S3 bucket that receives the frontend build."
  value       = local.frontend_bucket.id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution id (empty when CloudFront is disabled)."
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.frontend[0].id : ""
}

output "table_names" {
  description = "DynamoDB table names."
  value       = { for k, t in local.tables : k => t.name }
}

output "order_events_topic_arn" {
  description = "SNS topic carrying order lifecycle events."
  value       = aws_sns_topic.order_events.arn
}

output "alerts_topic_arn" {
  description = "SNS topic for operational (DLQ) alerts."
  value       = aws_sns_topic.alerts.arn
}

output "customer_email_topic_arn" {
  description = "SNS topic for customer emails (empty when disabled)."
  value       = var.enable_customer_email ? aws_sns_topic.customer_email[0].arn : ""
}

output "queue_urls" {
  description = "Work queue and DLQ URLs per service."
  value = {
    for k, _ in local.services : k => {
      queue = aws_sqs_queue.work[k].url
      dlq   = aws_sqs_queue.dlq[k].url
    }
  }
}

output "lambda_functions" {
  description = "Lambda function names."
  value       = { for k, f in aws_lambda_function.fn : k => f.function_name }
}

output "alarm_name_prefix" {
  description = "Prefix of all CloudWatch alarms created by this stack."
  value       = local.alarm_prefix
}

output "uses_lab_role" {
  description = "true when the functions run with the shared AWS Academy LabRole."
  value       = var.use_lab_role
}
