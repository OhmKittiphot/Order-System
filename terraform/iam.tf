# ---------------------------------------------------------------------------
# Execution roles
#
# AWS Academy Learner Lab does not allow iam:CreateRole, so by default every
# function uses the pre-provisioned LabRole (use_lab_role = true). This is a
# documented deviation from least privilege imposed by the lab.
#
# In a normal account set use_lab_role = false: Terraform then creates one
# role per function with only the actions and resources that function needs.
# ---------------------------------------------------------------------------

data "aws_iam_role" "lab" {
  count = var.use_lab_role ? 1 : 0
  name  = var.lab_role_name
}

locals {
  t   = local.tables
  idx = { for k, v in local.tables : k => "${v.arn}/index/*" }

  publish_events = {
    Effect   = "Allow"
    Action   = ["sns:Publish"]
    Resource = [aws_sns_topic.order_events.arn]
  }
  # Needed only when the topics use the AWS managed SNS key.
  sns_kms = {
    Effect   = "Allow"
    Action   = ["kms:GenerateDataKey*", "kms:Decrypt"]
    Resource = ["arn:${local.partition}:kms:${local.region}:${local.account_id}:key/*"]
    Condition = {
      StringEquals = { "kms:ViaService" = "sns.${local.region}.amazonaws.com" }
    }
  }

  worker_statements = {
    for name, _ in local.services : name => [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
        Resource = [aws_sqs_queue.work[name].arn]
      },
      {
        # Park permanently invalid messages in this worker's own DLQ.
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = [aws_sqs_queue.dlq[name].arn]
      },
    ]
  }

  function_statements = {
    # Stateless: verifies the token signature only.
    authorizer = []

    auth = concat([
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = [local.t.users.arn]

      },
      ], [for s in [{
        Effect   = "Allow"
        Action   = ["sns:Subscribe"]
        Resource = [for t in aws_sns_topic.customer_email : t.arn]
    }] : s if var.enable_customer_email])

    products = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query"]
        Resource = [local.t.products.arn, local.idx.products, local.t.inventory.arn]
      },
    ]

    orders = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:BatchGetItem"]
        Resource = [local.t.products.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:ConditionCheckItem"]
        Resource = [local.t.orders.arn, local.idx.orders, local.t.idempotency.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Query"]
        Resource = [local.idx.notifications]
      },
      local.publish_events,
      local.sns_kms,
    ]

    admin = [
      {
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"]
        Resource = [
          local.t.orders.arn, local.idx.orders,
          local.t.products.arn, local.idx.products,
          local.t.inventory.arn,
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Query"]
        Resource = [local.t.payments.arn, local.t.users.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:GetQueueAttributes"]
        Resource = concat([for q in aws_sqs_queue.work : q.arn], [for q in aws_sqs_queue.dlq : q.arn])
      },
      {
        # DLQ redrive (StartMessageMoveTask) needs read/delete on the DLQ and send on the source queue.
        Effect   = "Allow"
        Action   = ["sqs:StartMessageMoveTask", "sqs:ListMessageMoveTasks", "sqs:ReceiveMessage", "sqs:DeleteMessage"]
        Resource = [for q in aws_sqs_queue.dlq : q.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = [for q in aws_sqs_queue.work : q.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["cloudwatch:DescribeAlarms"]
        Resource = ["arn:${local.partition}:cloudwatch:${local.region}:${local.account_id}:alarm:${local.alarm_prefix}*"]
      },
      local.publish_events,
      local.sns_kms,
    ]

    stock = concat(local.worker_statements.stock, [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"]
        Resource = [local.t.orders.arn, local.t.inventory.arn]
      },
      local.publish_events,
      local.sns_kms,
    ])

    payment = concat(local.worker_statements.payment, [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"]
        Resource = [local.t.orders.arn, local.t.inventory.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:ConditionCheckItem"]
        Resource = [local.t.payments.arn]
      },
      local.publish_events,
      local.sns_kms,
    ])

    notify = concat(local.worker_statements.notify, [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = [local.t.orders.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = [local.t.notifications.arn]
      },
      ], [for s in [
        {
          Effect   = "Allow"
          Action   = ["sns:Publish"]
          Resource = [for t in aws_sns_topic.customer_email : t.arn]
        },
        local.sns_kms,
    ] : s if var.enable_customer_email])

    outbox = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Query", "dynamodb:UpdateItem"]
        Resource = [local.t.orders.arn, local.idx.orders]
      },
      local.publish_events,
      local.sns_kms,
    ]
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each = var.use_lab_role ? {} : local.functions

  name               = "${local.name_prefix}-${each.key}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda" {
  for_each = var.use_lab_role ? {} : local.functions

  name = "${local.name_prefix}-${each.key}-policy"
  role = aws_iam_role.lambda[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = ["${aws_cloudwatch_log_group.lambda[each.key].arn}:*"]
        }
      ],
      local.function_statements[each.key],
    )
  })
}

locals {
  lambda_role_arns = {
    for name, _ in local.functions :
    name => var.use_lab_role ? data.aws_iam_role.lab[0].arn : aws_iam_role.lambda[name].arn
  }
}
