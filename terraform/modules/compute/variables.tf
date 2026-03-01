variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC"
  type        = string
}

variable "subnet_ids" {
  description = "List of private subnet IDs"
  type        = list(string)
}

variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
}
