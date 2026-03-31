output "cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint of the EKS cluster"
  value       = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Certificate authority data for the EKS cluster"
  value       = module.eks.cluster_certificate_authority_data
}

output "cluster_security_group_id" {
  description = "Security group ID for the EKS cluster"
  value       = module.eks.cluster_security_group_id
}

output "node_security_group_id" {
  description = "Security group ID for the EKS nodes"
  value       = module.eks.node_security_group_id
}

output "karpenter_node_iam_role_arn" {
  description = "ARN of the IAM role for Karpenter nodes"
  value       = module.karpenter.node_iam_role_arn
}

output "karpenter_node_iam_role_name" {
  description = "Name of the IAM role for Karpenter nodes"
  value       = module.karpenter.node_iam_role_name
}

output "karpenter_queue_name" {
  description = "Name of the SQS queue for Karpenter"
  value       = module.karpenter.queue_name
}

output "karpenter_irsa_role_arn" {
  description = "ARN of the IAM role for Service Account for Karpenter"
  value       = module.karpenter.iam_role_arn
}

output "lb_controller_irsa_role_arn" {
  description = "ARN of the IAM role for Service Account for AWS Load Balancer Controller"
  value       = module.lb_controller_irsa_role.iam_role_arn
}

output "bastion_security_group_id" {
  description = "Security group ID of the bastion host"
  value       = aws_security_group.bastion_sg.id
}

output "bastion_instance_id" {
  description = "ID of the bastion host"
  value       = aws_instance.bastion.id
}

output "oidc_provider_arn" {
  description = "The ARN of the OIDC Provider for the EKS cluster"
  value       = module.eks.oidc_provider_arn
}
