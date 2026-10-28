# React build hosting. Default: S3 static website (as in the diagram).
# Optional: CloudFront + private bucket (HTTPS) with enable_cloudfront = true.
# Files are uploaded by scripts/deploy-frontend.sh after the build, because
# the build needs the API URL output by this configuration.

# The bucket itself is created with the AWS CLI, not aws_s3_bucket: that
# resource reads every bucket sub-configuration after create (object lock,
# acceleration, ...) and the AWS Academy SCP explicitly denies
# s3:GetBucketObjectLockConfiguration, so apply fails. The settings we need
# are still managed by the dedicated resources below.
# create-bucket is idempotent for a bucket you own in us-east-1 (the lab region).
locals {
  frontend_bucket_name = "${local.name_prefix}-web-${local.account_id}"
  frontend_bucket = {
    id                          = terraform_data.frontend_bucket.output.bucket
    arn                         = "arn:${local.partition}:s3:::${terraform_data.frontend_bucket.output.bucket}"
    bucket_regional_domain_name = "${terraform_data.frontend_bucket.output.bucket}.s3.${local.region}.amazonaws.com"
  }
}

resource "terraform_data" "frontend_bucket" {
  input = { bucket = local.frontend_bucket_name, region = local.region }

  # Interpreter-only commands keep this shell-independent (cmd.exe / bash).
  provisioner "local-exec" {
    interpreter = concat(
      ["aws", "s3api", "create-bucket", "--bucket", self.input.bucket, "--region", self.input.region],
      self.input.region == "us-east-1" ? [] : ["--create-bucket-configuration", "LocationConstraint=${self.input.region}"],
    )
    command = "--no-cli-pager"
  }

  # Lab-friendly: destroy also removes uploaded files.
  provisioner "local-exec" {
    when        = destroy
    interpreter = ["aws", "s3", "rb", "s3://${self.input.bucket}", "--force", "--region", self.input.region]
    command     = "--no-cli-pager"
  }
}

resource "aws_s3_bucket_ownership_controls" "frontend" {
  bucket = local.frontend_bucket.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = local.frontend_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --- Option A: public S3 website (enable_cloudfront = false) ---------------
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = local.frontend_bucket.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = var.enable_cloudfront
  restrict_public_buckets = var.enable_cloudfront
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  count  = var.enable_cloudfront ? 0 : 1
  bucket = local.frontend_bucket.id

  index_document {
    suffix = "index.html"
  }
  # SPA routing: unknown paths return index.html and React Router handles them.
  error_document {
    key = "index.html"
  }
}

# --- Option B: CloudFront with Origin Access Control -------------------------
resource "aws_cloudfront_origin_access_control" "frontend" {
  count                             = var.enable_cloudfront ? 1 : 0
  name                              = "${local.name_prefix}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  count               = var.enable_cloudfront ? 1 : 0
  enabled             = true
  comment             = "${local.name_prefix} frontend"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = local.frontend_bucket.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend[0].id
  }

  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = "658327ea-f89d-4fab-a63d-7e88639e58f6" # AWS managed "CachingOptimized"
  }

  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Bucket policy for whichever option is active.
resource "aws_s3_bucket_policy" "frontend" {
  bucket = local.frontend_bucket.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      # The S3 website endpoint is HTTP-only, so TLS can only be enforced on the bucket
      # when CloudFront (HTTPS) is the entry point.
      [for s in [{
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [local.frontend_bucket.arn, "${local.frontend_bucket.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }] : s if var.enable_cloudfront],
      [for s in [{
        Sid       = "PublicReadWebsite"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${local.frontend_bucket.arn}/*"
      }] : s if !var.enable_cloudfront],
      [for d in aws_cloudfront_distribution.frontend : {
        Sid       = "CloudFrontReadOnly"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${local.frontend_bucket.arn}/*"
        Condition = { StringEquals = { "AWS:SourceArn" = d.arn } }
      }],
    )
  })

  depends_on = [aws_s3_bucket_public_access_block.frontend]
}
