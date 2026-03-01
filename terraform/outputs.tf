output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "ecr_repository_urls" {
  value = module.ecr.repository_urls
}

output "s3_bucket_names" {
  value = module.s3_cdn.bucket_names
}

output "cloudfront_domain_name" {
  value = module.s3_cdn.cloudfront_domain_name
}

output "rds_endpoint" {
  value = module.rds.db_endpoint
}

output "amplify_app_id" {
  value = module.amplify.amplify_app_id
}

output "amplify_default_domain" {
  value = module.amplify.amplify_default_domain
}
