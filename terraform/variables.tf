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

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "private_subnets" {
  description = "Private subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnets" {
  description = "Public subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
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
