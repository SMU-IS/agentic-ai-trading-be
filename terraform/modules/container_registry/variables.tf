variable "services" {
  description = "List of service names for ECR repositories"
  type        = list(string)
}

variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
}
