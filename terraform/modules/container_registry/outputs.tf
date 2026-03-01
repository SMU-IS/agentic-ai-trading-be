output "repository_urls" {
  description = "Map of service names to ECR repository URLs"
  value       = { for k, v in aws_ecr_repository.services : k => v.repository_url }
}

output "repository_names" {
  description = "List of ECR repository names"
  value       = [for repo in aws_ecr_repository.services : repo.name]
}
