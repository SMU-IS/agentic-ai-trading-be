# =============================================================================
# S3 Buckets and CloudFront CDN Outputs
# =============================================================================

output "bucket_names" {
  description = "Map of bucket names (newly created + existing)"
  value = merge(
    { for k, v in aws_s3_bucket.new_buckets : k => v.bucket },
    { for k, v in aws_s3_bucket.existing_buckets : k => v.bucket }
  )
}

output "bucket_arns" {
  description = "Map of bucket ARNs (newly created + existing)"
  value = merge(
    { for k, v in aws_s3_bucket.new_buckets : k => v.arn },
    { for k, v in aws_s3_bucket.existing_buckets : k => v.arn }
  )
}

output "new_bucket_names" {
  description = "Map of newly created bucket names"
  value       = { for k, v in aws_s3_bucket.new_buckets : k => v.bucket }
}

output "existing_bucket_names" {
  description = "Map of imported existing bucket names"
  value       = { for k, v in aws_s3_bucket.existing_buckets : k => v.bucket }
}
