variable "cluster_name" {
  description = "Name of the cluster (used for resource naming)"
  type        = string
}

variable "amplify_repository" {
  description = "GitHub/GitLab repository URL for Amplify"
  type        = string
}

variable "amplify_access_token" {
  description = "Personal Access Token for the repository"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
}
