variable "kong_lb_dns" {
  description = "The DNS name of the Kong NLB"
  type        = string
}

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

variable "base_api_url" {
  description = "Base API URL for the application"
  type        = string
}

variable "chat_api_url" {
  description = "Chat API URL"
  type        = string
}

variable "finnhub_api_key" {
  description = "Finnhub API Key"
  type        = string
  sensitive   = true
}

variable "logokit_api_key" {
  description = "Logokit API Key"
  type        = string
  sensitive   = true
}

variable "notif_api_url" {
  description = "Notification API URL"
  type        = string
}

variable "thread_api_url" {
  description = "Thread API URL"
  type        = string
}

variable "enable_sign_up" {
  description = "Flag to toggle sign up functionality"
  type        = bool
  default     = false
}

variable "show_banner" {
  description = "Flag to toggle banner display"
  type        = bool
  default     = false
}

variable "banner_message" {
  description = "Message to display in the banner"
  type        = string
  default     = ""
}

variable "show_cloudwatch_metrics" {
  description = "Flag to toggle CloudWatch metrics display"
  type        = bool
  default     = false
}
