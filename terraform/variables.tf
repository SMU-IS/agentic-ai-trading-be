variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "agentic-m-cluster"
}

variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "enable_waf" {
  description = "Toggle to enable or disable the WAF (saves $10+/mo when false)"
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "private_subnets" {
  description = "Private subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "public_subnets" {
  description = "Public subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24"]
}

variable "services" {
  description = "List of microservices to create ECR repositories for"
  type        = list(string)
  default = [
    "ticker-identification-service",
    "event-identification-service",
    "news-aggregator-service",
    "news-scraper",
    "notification-alert",
    "preprocessing-service",
    "qdrant-retrieval",
    "rag-chatbot",
    "sentiment-analysis-service",
    "trading-agent-m",
    "trading-service",
    "user-info",
    "news-scraper-tradingview",
    "metrics-tracker-service",
    "info-agent-service"
  ]
}

variable "s3_buckets" {
  description = "Map of S3 bucket keys to their specific names"
  type        = map(string)
  default = {
    "prompt-template" = "s3-prompt-template"
  }
}

variable "db_configs" {
  description = "Map of database configurations"
  type = map(object({
    db_name  = string
    username = string
    password = string
  }))
  default = {
    "trading" = {
      db_name  = "ragbotdb"
      username = "ragbotadmin"
      password = ""
    }
  }
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

variable "base_api_url" {
  type      = string
  sensitive = true
}
variable "chat_api_url" {
  type      = string
  sensitive = true
}
variable "finnhub_api_key" {
  type      = string
  sensitive = true
}
variable "logokit_api_key" {
  type      = string
  sensitive = true
}
variable "notif_api_url" {
  type      = string
  sensitive = true
}
variable "thread_api_url" {
  type      = string
  sensitive = true
}

variable "jwt_secret" {
  type        = string
  description = "Secret used for signing and verifying JWTs"
  sensitive   = true
}

variable "enable_sign_up" {
  type      = bool
  sensitive = true
}

variable "show_banner" {
  type      = bool
  sensitive = true
}

variable "banner_message" {
  type      = string
  sensitive = true
}

variable "show_cloudwatch_metrics" {
  type      = bool
  sensitive = true
}

variable "kong_redis_host" {
  description = "Redis host for Kong rate-limiting"
  type        = string
}

variable "kong_redis_port" {
  description = "Redis port for Kong rate-limiting"
  type        = number
  default     = 6379
}

variable "kong_redis_password" {
  description = "Redis password for Kong rate-limiting"
  type        = string
  sensitive   = true
}

# =============================================================================
# Terraform State Backend Configuration
# =============================================================================

variable "terraform_state_bucket" {
  description = "S3 bucket name for Terraform state storage"
  type        = string
  default     = "agentm-terraform-state"
}

variable "terraform_state_key" {
  description = "S3 key path for Terraform state file"
  type        = string
  default     = "terraform.tfstate"
}
