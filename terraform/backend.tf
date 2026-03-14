# =============================================================================
# Terraform Remote State Backend (S3)
# =============================================================================

terraform {
  backend "s3" {
    bucket  = "agentm-terraform-state"
    key     = "terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
