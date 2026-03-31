# =============================================================================
# Amazon Managed Service for Prometheus (AMP)
# =============================================================================

resource "aws_prometheus_workspace" "main" {
  alias = "${var.cluster_name}-workspace"

  tags = {
    Environment = var.environment
  }
}

# IAM Role for Prometheus Service Account (IRSA)
# This role allows the Prometheus agent running in EKS to write metrics to AMP
module "amp_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name                                       = "${var.cluster_name}-amp-prometheus"
  attach_amazon_managed_service_prometheus_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.compute.oidc_provider_arn
      namespace_service_accounts = ["monitoring:prometheus-amp-server"]
    }
  }

  tags = {
    Environment = var.environment
  }
}

# =============================================================================
# Amazon Managed Grafana (AMG)
# =============================================================================

resource "aws_grafana_workspace" "main" {
  name                     = "${var.cluster_name}-grafana-v2"
  account_access_type      = "CURRENT_ACCOUNT"
  authentication_providers = ["AWS_SSO"]
  permission_type          = "SERVICE_MANAGED"
  data_sources             = ["PROMETHEUS"]

  # Grafana needs an IAM role to assume to access data sources
  role_arn = aws_iam_role.grafana.arn

  tags = {
    Environment = var.environment
  }
}

# IAM Role for Managed Grafana
resource "aws_iam_role" "grafana" {
  name = "${var.cluster_name}-grafana-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "grafana.amazonaws.com"
        }
      },
    ]
  })

  tags = {
    Environment = var.environment
  }
}

# Attach policy to Grafana role to allow it to read from AMP
resource "aws_iam_role_policy_attachment" "grafana_amp_read" {
  role       = aws_iam_role.grafana.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonPrometheusQueryAccess"
}
