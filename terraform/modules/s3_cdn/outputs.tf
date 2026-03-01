output "bucket_names" {
  value = { for k, v in aws_s3_bucket.buckets : k => v.id }
}

output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.s3_distribution.domain_name
}
