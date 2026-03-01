variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "agentic-trading-cluster"
}

variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "services" {
  description = "List of microservices to create ECR repositories for"
  type        = list(string)
  default = [
    "news-aggregator-service",
    "news-analysis",
    "news-scraper",
    "notification-alert",
    "qdrant-retrieval",
    "rag-chatbot",
    "trading-agent-m",
    "trading-service",
    "user-info"
  ]
}

variable "s3_buckets" {
  description = "Map of S3 bucket keys to their specific names"
  type        = map(string)
  default = {
    "assets"          = "agentic-trading-assets"
    "prompt-template" = "s3-prompt-template"
  }
}

variable "db_name" {
  description = "Name of the RDS database"
  type        = string
  default     = "tradingdb"
}

variable "db_username" {
  description = "Username for the RDS database"
  type        = string
  default     = "dbadmin"
}

variable "db_password" {
  description = "Password for the RDS database"
  type        = string
  sensitive   = true
}

variable "amplify_repository" {
  description = "GitHub/GitLab repository URL for Amplify"
  type        = string
  default     = "https://github.com/SMU-IS/agentic-ai-trading-fe"
}

variable "amplify_access_token" {
  description = "Personal Access Token for the repository (GitHub/GitLab)"
  type        = string
  sensitive   = true
}
