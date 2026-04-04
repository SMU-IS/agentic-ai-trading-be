# =============================================================================
# Infrastructure Outputs (Infrastructure-Centric Structure)
# =============================================================================

# -----------------------------------------------------------------------------
# Networking
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# EKS Cluster (Compute)
# -----------------------------------------------------------------------------
output "cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.compute.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint of the EKS cluster"
  value       = module.compute.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Certificate authority data for the EKS cluster"
  value       = module.compute.cluster_certificate_authority_data
  sensitive   = true
}

output "cluster_security_group_id" {
  description = "Security group ID for the EKS cluster"
  value       = module.compute.cluster_security_group_id
}

output "node_security_group_id" {
  description = "Security group ID for the EKS nodes"
  value       = module.compute.node_security_group_id
}

output "oidc_provider_arn" {
  description = "The ARN of the OIDC Provider for the EKS cluster"
  value       = module.compute.oidc_provider_arn
}

# -----------------------------------------------------------------------------
# Kubernetes Controller & Node Roles
# -----------------------------------------------------------------------------
output "karpenter_node_iam_role_arn" {
  description = "ARN of the IAM role for Karpenter nodes"
  value       = module.compute.karpenter_node_iam_role_arn
}

output "karpenter_irsa_role_arn" {
  description = "ARN of the IAM role for Service Account for Karpenter"
  value       = module.compute.karpenter_irsa_role_arn
}

output "lb_controller_irsa_role_arn" {
  description = "ARN of the IAM role for Service Account for AWS Load Balancer Controller"
  value       = module.compute.lb_controller_irsa_role_arn
}

# -----------------------------------------------------------------------------
# Bastion Host
# -----------------------------------------------------------------------------
output "bastion_instance_id" {
  description = "ID of the bastion host"
  value       = module.compute.bastion_instance_id
}

output "bastion_security_group_id" {
  description = "Security group ID of the bastion host"
  value       = module.compute.bastion_security_group_id
}

# -----------------------------------------------------------------------------
# Container Registry (ECR)
# -----------------------------------------------------------------------------
output "ecr_repository_urls" {
  description = "Map of service names to ECR repository URLs"
  value       = module.container_registry.repository_urls
}

output "ecr_repository_names" {
  description = "List of ECR repository names"
  value       = module.container_registry.repository_names
}

# -----------------------------------------------------------------------------
# Storage (S3)
# -----------------------------------------------------------------------------
output "s3_bucket_names" {
  description = "Map of bucket names"
  value       = module.storage.bucket_names
}

output "s3_bucket_arns" {
  description = "Map of bucket ARNs"
  value       = module.storage.bucket_arns
}

# -----------------------------------------------------------------------------
# Databases (RDS)
# -----------------------------------------------------------------------------
output "rds_endpoints" {
  description = "Endpoints of the RDS instances"
  value       = { for k, v in module.databases : k => v.db_endpoint }
}

output "rds_db_names" {
  description = "Database names of the RDS instances"
  value       = { for k, v in module.databases : k => v.db_name }
}

output "rds_instance_ids" {
  description = "Identifiers of the RDS instances"
  value       = { for k, v in module.databases : k => v.db_instance_id }
}

output "rds_security_group_ids" {
  description = "IDs of the RDS security groups"
  value       = { for k, v in module.databases : k => v.db_security_group_id }
}

# -----------------------------------------------------------------------------
# Web Hosting (Amplify)
# -----------------------------------------------------------------------------
output "amplify_app_id" {
  description = "ID of the Amplify app"
  value       = module.hosting.amplify_app_id
}

output "amplify_default_domain" {
  description = "Default domain of the Amplify app"
  value       = module.hosting.amplify_default_domain
}

output "amplify_custom_domain" {
  description = "Custom domain of the Amplify app"
  value       = module.hosting.custom_domain_name
}

# -----------------------------------------------------------------------------
# Application / API
# -----------------------------------------------------------------------------
output "backend_api_url" {
  description = "The DNS name of the Kong Gateway Load Balancer"
  value       = try(data.kubernetes_service.kong_proxy.status[0].load_balancer[0].ingress[0].hostname, "Waiting for Load Balancer...")
}

# -----------------------------------------------------------------------------
# Monitoring & Observability
# -----------------------------------------------------------------------------
# output "prometheus_workspace_id" {
#   description = "ID of the AMP workspace"
#   value       = aws_prometheus_workspace.main.id
# }

# output "prometheus_endpoint" {
#   description = "Endpoint for Prometheus Remote Write"
#   value       = aws_prometheus_workspace.main.prometheus_endpoint
# }

output "grafana_url" {
  description = "URL for the Grafana workspace"
  value       = "https://${aws_grafana_workspace.main.endpoint}"
}

# output "amp_irsa_role_arn" {
#   description = "ARN of the IAM role for the Prometheus agent in EKS"
#   value       = module.amp_irsa_role.iam_role_arn
# }

output "metrics_tracker_irsa_role_arn" {
  description = "ARN of the IAM role for the Metrics Tracker service in EKS"
  value       = module.metrics_tracker_irsa_role.iam_role_arn
}

output "fluent_bit_irsa_role_arn" {
  description = "ARN of the IAM role for Fluent Bit in EKS"
  value       = module.fluent_bit_irsa_role.iam_role_arn
}

output "aws_region" {
  description = "The AWS region where resources are deployed"
  value       = var.aws_region
}
