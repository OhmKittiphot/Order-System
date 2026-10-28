# AWS Serverless Order Management System
#
# Resources are split by concern; this file is the map.
#
#   api_gateway.tf  HTTP API, Lambda Authorizer (JWT), routes, stage, access logs
#   lambda.tf       Deployment package, 9 functions (incl. authorizer), JWT secret, SQS event sources, outbox schedule
#   iam.tf          LabRole (Academy) or per-function least-privilege roles
#   dynamodb.tf     Orders, Products, Inventory, Payments, Notifications, Users, Idempotency
#   sns.tf          order-events topic + filtered SQS subscriptions, customer-email topic
#   sqs.tf          stock/payment/notify queues, their DLQs, queue policies
#   monitoring.tf   DLQ / queue-age / Lambda-error / API-5xx alarms -> dlq-alerts topic
#   frontend.tf     S3 website (default) or private S3 + CloudFront
#
# Request flow
#   Browser -> API Gateway (Lambda Authorizer verifies JWT) -> Order Lambda -> Orders table (PENDING + outbox marker)
#           -> SNS order-events --OrderPlaced-->       stock-queue   -> Stock Lambda   -> Inventory (reserve)
#                               --InventoryReserved--> payment-queue -> Payment Lambda -> Payments (+ commit/release stock)
#                               --OrderConfirmed/Failed--> notify-queue -> Notify Lambda -> Notifications (+ customer email SNS)
#   Any queue: 3 failed receives -> DLQ -> CloudWatch alarm -> dlq-alerts SNS -> admin email
#
# Deployment order is handled by Terraform's dependency graph:
# tables/topics/queues/JWT secret -> Lambda (env vars reference them) ->
# event source mappings / API integrations -> stage.
