variable "s3_buckets" {
  description = "Map of S3 bucket keys to their specific names"
  type        = map(string)
}

variable "import_existing_buckets" {
  description = "Map of bucket keys to existing bucket names to import. Use when bucket already exists. Example: { assets = \"my-existing-assets-bucket\" }"
  type        = map(string)
  default     = {}
}

variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
}
