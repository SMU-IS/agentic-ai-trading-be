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

# Lifecycle rule to move objects to Intelligent-Tiering to save costs
resource "aws_s3_bucket_lifecycle_configuration" "new_buckets_lifecycle" {
  for_each = local.buckets_to_create

  bucket = aws_s3_bucket.new_buckets[each.key].id

  rule {
    id     = "move-to-intelligent-tiering"
    status = "Enabled"

    filter {}

    transition {
      days          = 30
      storage_class = "INTELLIGENT_TIERING"
    }
  }
}

# =============================================================================
# Import Existing Buckets
# =============================================================================
resource "aws_s3_bucket" "existing_buckets" {
  for_each = var.import_existing_buckets

  bucket = each.value

  tags = {
    Name        = each.key
    Environment = var.environment
  }
}

# Lifecycle rule for existing buckets
resource "aws_s3_bucket_lifecycle_configuration" "existing_buckets_lifecycle" {
  for_each = var.import_existing_buckets

  bucket = aws_s3_bucket.existing_buckets[each.key].id

  rule {
    id     = "move-to-intelligent-tiering"
    status = "Enabled"

    filter {}

    transition {
      days          = 30
      storage_class = "INTELLIGENT_TIERING"
    }
  }
}

# =============================================================================
# Public Access Block for new buckets
# =============================================================================
resource "aws_s3_bucket_public_access_block" "new_buckets_access" {
  for_each = local.buckets_to_create

  bucket = aws_s3_bucket.new_buckets[each.key].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# =============================================================================
# Public Access Block for existing buckets
# =============================================================================
resource "aws_s3_bucket_public_access_block" "existing_buckets_access" {
  for_each = var.import_existing_buckets

  bucket = aws_s3_bucket.existing_buckets[each.key].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
