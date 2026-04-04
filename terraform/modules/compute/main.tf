# =============================================================================
# EKS Cluster Configuration with Karpenter
# =============================================================================

# Latest Amazon Linux 2023 AMI for bastion
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-arm64"]
  }

  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

# EKS Cluster with Karpenter enabled
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.35"

  # Grant cluster creator administrative access
  enable_cluster_creator_admin_permissions = true

  vpc_id     = var.vpc_id
  subnet_ids = var.subnet_ids

  # Cluster endpoint - enable public for TF provider access
  cluster_endpoint_private_access = true
  cluster_endpoint_public_access  = true

  # Disable cluster logging to save cost
  cluster_enabled_log_types   = []
  create_cloudwatch_log_group = false

  # Managed Node Group for system pods (Karpenter, CoreDNS)
  eks_managed_node_groups = {
    system = {
      ami_type       = "AL2023_ARM_64_STANDARD"
      instance_types = ["t4g.small"]
      capacity_type  = "ON_DEMAND"

      # Essential for public nodes to reach EKS control plane
      associate_public_ip_address = true

      min_size     = 1
      max_size     = 2
      desired_size = 1

      labels = {
        "node.kubernetes.io/scope" = "system"
      }
    }
  }

  tags = {
    Environment = var.environment
  }
}

# AWS Load Balancer Controller - IAM Role for Service Accounts (IRSA)
module "lb_controller_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name                              = "${var.cluster_name}-lb-controller"
  attach_load_balancer_controller_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }

  tags = {
    Environment = var.environment
  }
}

# Karpenter
module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 20.0"

  cluster_name = module.eks.cluster_name

  # Enable full permissions for Karpenter to manage nodes
  enable_irsa                     = true
  irsa_oidc_provider_arn          = module.eks.oidc_provider_arn
  irsa_namespace_service_accounts = ["kube-system:karpenter"]

  # IAM role for nodes
  create_node_iam_role = true

  tags = {
    Environment = var.environment
  }
}
