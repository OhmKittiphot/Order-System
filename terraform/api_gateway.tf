# HTTP API with a Lambda Authorizer ("Lambda Authorizer - verify JWT" in the
# diagram). It verifies the HS256 access token issued by the Auth Lambda
# (signature, issuer, type, expiry) before any protected Lambda runs. A
# missing header gets 401 from the gateway, a rejected token 403. Role checks
# on admin routes happen in code (403).

locals {
  # route key => { fn = lambda key, auth = JWT required }
  # Must match backend/local/order_system_local/routes.py (checked by tests).
  api_routes = {
    "POST /auth/register"                     = { fn = "auth", auth = false }
    "POST /auth/login"                        = { fn = "auth", auth = false }
    "POST /auth/refresh"                      = { fn = "auth", auth = false }
    "GET /me"                                 = { fn = "auth", auth = true }
    "GET /products"                           = { fn = "products", auth = false }
    "GET /products/{productId}"               = { fn = "products", auth = false }
    "POST /orders"                            = { fn = "orders", auth = true }
    "GET /orders"                             = { fn = "orders", auth = true }
    "GET /orders/{orderId}"                   = { fn = "orders", auth = true }
    "GET /notifications"                      = { fn = "orders", auth = true }
    "GET /admin/orders"                       = { fn = "admin", auth = true }
    "GET /admin/orders/{orderId}"             = { fn = "admin", auth = true }
    "POST /admin/orders/{orderId}/retry"      = { fn = "admin", auth = true }
    "POST /admin/orders/{orderId}/cancel"     = { fn = "admin", auth = true }
    "GET /admin/products"                     = { fn = "admin", auth = true }
    "POST /admin/products"                    = { fn = "admin", auth = true }
    "GET /admin/products/{productId}"         = { fn = "admin", auth = true }
    "PATCH /admin/products/{productId}"       = { fn = "admin", auth = true }
    "PATCH /admin/products/{productId}/stock" = { fn = "admin", auth = true }
    "GET /admin/stats"                        = { fn = "admin", auth = true }
    "GET /admin/dlq-status"                   = { fn = "admin", auth = true }
    "POST /admin/dlq/{queue}/redrive"         = { fn = "admin", auth = true }
  }

  api_functions = toset(distinct([for r in values(local.api_routes) : r.fn]))

  frontend_origin = var.enable_cloudfront ? "https://${aws_cloudfront_distribution.frontend[0].domain_name}" : "http://${aws_s3_bucket_website_configuration.frontend[0].website_endpoint}"
  cors_origins    = distinct(concat([local.frontend_origin], var.cors_allowed_origins))
}

resource "aws_apigatewayv2_api" "http" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"
  description   = "Order Management System API"

  cors_configuration {
    allow_origins  = local.cors_origins
    allow_methods  = ["GET", "POST", "PATCH", "OPTIONS"]
    allow_headers  = ["authorization", "content-type", "idempotency-key", "x-correlation-id"]
    expose_headers = ["x-correlation-id"]
    max_age        = 600
  }
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id                            = aws_apigatewayv2_api.http.id
  name                              = "lambda-jwt"
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.fn["authorizer"].invoke_arn
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
  identity_sources                  = ["$request.header.Authorization"]
  # Cached per token; keep below the access-token lifetime.
  authorizer_result_ttl_in_seconds = 300
}

resource "aws_lambda_permission" "authorizer" {
  statement_id  = "AllowHttpApiAuthorizerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn["authorizer"].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/authorizers/${aws_apigatewayv2_authorizer.jwt.id}"
}

resource "aws_apigatewayv2_integration" "lambda" {
  for_each = local.api_functions

  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.fn[each.key].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 15000
}

resource "aws_apigatewayv2_route" "routes" {
  for_each = local.api_routes

  api_id             = aws_apigatewayv2_api.http.id
  route_key          = each.key
  target             = "integrations/${aws_apigatewayv2_integration.lambda[each.value.fn].id}"
  authorization_type = each.value.auth ? "CUSTOM" : "NONE"
  authorizer_id      = each.value.auth ? aws_apigatewayv2_authorizer.jwt.id : null
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${local.name_prefix}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = var.api_throttle_rate_limit
    throttling_burst_limit = var.api_throttle_burst_limit
  }

  # No Authorization header or body is logged.
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      latencyMs      = "$context.responseLatency"
      integrationErr = "$context.integrationErrorMessage"
      authorizerErr  = "$context.authorizer.error"
      userId         = "$context.authorizer.userId"
      sourceIp       = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
    })
  }
}

resource "aws_lambda_permission" "api" {
  for_each = local.api_functions

  statement_id  = "AllowHttpApiInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
