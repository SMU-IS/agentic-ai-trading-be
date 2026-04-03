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
      namespace_service_accounts = ["monitoring:adot-collector", "amazon-metrics:adot-collector-sa"]
    }
  }

  tags = {
    Environment = var.environment
  }
}

# =============================================================================
# ADOT Collector for Prometheus Metrics (Restricted to specific services)
# =============================================================================

resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = "monitoring"
  }
}

resource "helm_release" "adot_collector" {
  name       = "adot-collector"
  repository = "https://aws-observability.github.io/aws-otel-helm-charts"
  chart      = "adot-exporter-for-eks-on-ec2"
  version    = "0.22.0"
  namespace  = "amazon-metrics"
  create_namespace = true

  set {
    name  = "awsRegion"
    value = var.aws_region
  }

  set {
    name  = "clusterName"
    value = var.cluster_name
  }

  set {
    name  = "adotCollector.daemonSet.serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = module.amp_irsa_role.iam_role_arn
  }

  set {
    name  = "adotCollector.daemonSet.serviceAccount.name"
    value = "adot-collector-sa"
  }

  # Override config to strictly only scrape the requested services
  values = [
    <<-EOT
    adotCollector:
      daemonSet:
        adotConfig:
          configFile: |
            extensions:
              sigv4auth:
                region: ${var.aws_region}
                service: "aps"

            receivers:
              prometheus:
                config:
                  global:
                    scrape_interval: 60s
                    scrape_timeout: 15s
                  scrape_configs:
                    - job_name: 'kubernetes-pods'
                      kubernetes_sd_configs:
                        - role: pod
                      relabel_configs:
                        - source_labels: [__meta_kubernetes_pod_label_app_kubernetes_io_instance]
                          action: keep
                          regex: (rag-chatbot|trading-agent-m|news-aggregator-service|trading-service)
                        - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
                          action: keep
                          regex: true
                        - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
                          action: replace
                          target_label: __metrics_path__
                          regex: (.+)
                        - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
                          action: replace
                          regex: ([^:]+)(?::\d+)?;(\d+)
                          replacement: $1:$2
                          target_label: __address__
                        - action: labelmap
                          regex: __meta_kubernetes_pod_label_(.+)
                        - source_labels: [__meta_kubernetes_namespace]
                          action: replace
                          target_label: kubernetes_namespace
                        - source_labels: [__meta_kubernetes_pod_name]
                          action: replace
                          target_label: kubernetes_pod_name
                      metric_relabel_configs:
                        - source_labels: [__name__]
                          regex: '^(http_requests_total|http_request_duration_seconds_.*|up)$'
                          action: keep

            processors:
              batch:
                timeout: 60s

            exporters:
              prometheusremotewrite:
                endpoint: "${aws_prometheus_workspace.main.prometheus_endpoint}api/v1/remote_write"
                auth:
                  authenticator: sigv4auth

            service:
              extensions: [sigv4auth]
              pipelines:
                metrics:
                  receivers: [prometheus]
                  processors: [batch]
                  exporters: [prometheusremotewrite]
    EOT
  ]

  depends_on = [
    module.compute,
    aws_prometheus_workspace.main,
    module.amp_irsa_role
  ]
}

# IAM Role for Metrics Tracker Service (IRSA)
# This role allows the metrics-tracker to query AMP and CloudWatch
module "metrics_tracker_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${var.cluster_name}-metrics-tracker"

  oidc_providers = {
    main = {
      provider_arn               = module.compute.oidc_provider_arn
      namespace_service_accounts = ["default:metrics-tracker-service-infra"]
    }
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "metrics_tracker_amp_query" {
  role       = module.metrics_tracker_irsa_role.iam_role_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonPrometheusQueryAccess"
}

resource "aws_iam_role_policy_attachment" "metrics_tracker_cw_read" {
  role       = module.metrics_tracker_irsa_role.iam_role_name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess"
}

resource "aws_iam_role_policy_attachment" "metrics_tracker_s3_full" {
  role       = module.metrics_tracker_irsa_role.iam_role_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

# =============================================================================
# Amazon Managed Grafana (AMG)
# =============================================================================

resource "aws_grafana_workspace" "main" {
  name                     = "${var.cluster_name}-grafana-v2"
  account_access_type      = "CURRENT_ACCOUNT"
  authentication_providers = ["AWS_SSO"]
  permission_type          = "SERVICE_MANAGED"
  data_sources             = ["PROMETHEUS", "CLOUDWATCH"]

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

# Attach policy to Grafana role to allow it to read from CloudWatch
resource "aws_iam_role_policy_attachment" "grafana_cloudwatch_read" {
  role       = aws_iam_role.grafana.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess"
}

# IAM Role for Fluent Bit Service Account (IRSA)
# This role allows Fluent Bit to create log groups and push logs to CloudWatch
module "fluent_bit_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name                           = "${var.cluster_name}-fluent-bit"
  attach_cloudwatch_observability_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.compute.oidc_provider_arn
      namespace_service_accounts = ["logging:fluent-bit"]
    }
  }

  tags = {
    Environment = var.environment
  }
}
