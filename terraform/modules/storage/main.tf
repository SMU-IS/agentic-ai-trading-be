# =============================================================================
# S3 Buckets and CloudFront CDN
# Supports both creating new buckets and importing existing ones
# =============================================================================

# =============================================================================
# New Buckets (created by Terraform)
# Only create buckets not in the import_existing_buckets list
# =============================================================================
locals {
  buckets_to_create = {
    for k, v in var.s3_buckets : k => v
    if !contains(keys(var.import_existing_buckets), k)
  }
}

resource "aws_s3_bucket" "new_buckets" {
  for_each = local.buckets_to_create

  bucket = "${each.value}-${var.environment}"

  tags = {
    Name        = each.key
    Environment = var.environment
  }
}

# =============================================================================
# Import Existing Buckets
# Use: terraform import module.storage.aws_s3_bucket.existing_buckets["assets"] actual-bucket-name
# =============================================================================
resource "aws_s3_bucket" "existing_buckets" {
  for_each = var.import_existing_buckets

  bucket = each.value

  tags = {
    Name        = each.key
    Environment = var.environment
  }
}

# =============================================================================
# Public Access Block for new buckets
# =============================================================================
resource "aws_s3_bucket_public_access_block" "new_buckets_access" {
  for_each = aws_s3_bucket.new_buckets

  bucket = each.value.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# =============================================================================
# Public Access Block for existing buckets
# =============================================================================
resource "aws_s3_bucket_public_access_block" "existing_buckets_access" {
  for_each = aws_s3_bucket.existing_buckets

  bucket = each.value.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# =============================================================================
# CloudFront Origin Access Control
# =============================================================================
resource "aws_cloudfront_origin_access_control" "default" {
  name                              = "assets-oac"
  description                       = "OAC for assets S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# =============================================================================
# CloudFront Distribution for Assets
# Uses the first available bucket (priority: new > existing)
# =============================================================================
data "aws_s3_bucket" "assets" {
  bucket = try(
    aws_s3_bucket.new_buckets["assets"].bucket,
    aws_s3_bucket.existing_buckets["assets"].bucket,
    null
  )
}

resource "aws_cloudfront_distribution" "s3_distribution" {
  count = contains(keys(var.s3_buckets), "assets") ? 1 : 0

  origin {
    domain_name              = try(
      data.aws_s3_bucket.assets.bucket_regional_domain_name,
      ""
    )
    origin_access_control_id = aws_cloudfront_origin_access_control.default.id
    origin_id                = "S3-assets"
  }

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "CDN for ${var.environment} assets"
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-assets"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Environment = var.environment
  }
}

# =============================================================================
# S3 Bucket Policy for CloudFront Access
# =============================================================================
resource "aws_s3_bucket_policy" "allow_cloudfront_access" {
  count = contains(keys(var.s3_buckets), "assets") ? 1 : 0

  bucket = try(
    aws_s3_bucket.new_buckets["assets"].id,
    aws_s3_bucket.existing_buckets["assets"].id,
    ""
  )

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "s3:GetObject"
        Effect   = "Allow"
        Resource = "${try(
          aws_s3_bucket.new_buckets["assets"].arn,
          aws_s3_bucket.existing_buckets["assets"].arn,
          ""
        )}/*"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.s3_distribution[0].arn
          }
        }
      }
    ]
  })
}
