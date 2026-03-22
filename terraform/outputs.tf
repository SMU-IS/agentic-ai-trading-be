# =============================================================================
# Infrastructure Outputs (Infrastructure-Centric Structure)
# =============================================================================

output "cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.compute.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint of the EKS cluster"
  value       = module.compute.cluster_endpoint
}

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.networking.vpc_id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC"
  value       = module.networking.vpc_cidr_block
}

output "private_subnet_ids" {
  description = "List of private subnet IDs"
  value       = module.networking.private_subnet_ids
}

output "public_subnet_ids" {
  description = "List of public subnet IDs"
  value       = module.networking.public_subnet_ids
}

output "ecr_repository_urls" {
  description = "Map of service names to ECR repository URLs"
  value       = module.container_registry.repository_urls
}

output "s3_bucket_names" {
  description = "Map of bucket names"
  value       = module.storage.bucket_names
}

output "s3_bucket_arns" {
  description = "Map of bucket ARNs"
  value       = module.storage.bucket_arns
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = module.hosting.cloudfront_domain_name
}

output "cloudfront_id" {
  description = "CloudFront distribution ID"
  value       = module.hosting.cloudfront_id
}

output "rds_endpoints" {
  description = "Endpoints of the RDS instances"
  value       = { for k, v in module.databases : k => v.db_endpoint }
}

output "rds_security_group_ids" {
  description = "IDs of the RDS security groups"
  value       = { for k, v in module.databases : k => v.db_security_group_id }
}

output "amplify_app_id" {
  description = "ID of the Amplify app"
  value       = module.hosting.amplify_app_id
}

output "amplify_default_domain" {
  description = "Default domain of the Amplify app"
  value       = module.hosting.amplify_default_domain
}

output "backend_api_url" {
  description = "The DNS name of the Kong Gateway Load Balancer"
  value       = try(data.kubernetes_service.kong_proxy.status[0].load_balancer[0].ingress[0].hostname, "Waiting for Load Balancer...")
}
