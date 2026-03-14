# =============================================================================
# networking         - VPC, subnets, NAT gateways (none - public nodes for cost)
# compute            - EKS cluster with Karpenter (spot instances, t4g.small system, t4g.micro apps)
# databases          - RDS (db.t4g.micro - smallest available Graviton)
# storage            - S3 buckets, CloudFront CDN
# container_registry - ECR repositories
# hosting            - Amplify app, branches
# =============================================================================

# Networking Module
module "networking" {
  source          = "./modules/networking"
  cluster_name    = var.cluster_name
  vpc_cidr        = var.vpc_cidr
  azs             = var.azs
  private_subnets = var.private_subnets
  public_subnets  = var.public_subnets
  environment     = var.environment
}

# Compute Module (EKS with Karpenter - Public Spot Instances)
module "compute" {
  source       = "./modules/compute"
  cluster_name = var.cluster_name
  vpc_id       = module.networking.vpc_id
  subnet_ids   = module.networking.public_subnet_ids
  environment  = var.environment
}

# Databases Module (db.t4g.micro - smallest RDS instance)
module "databases" {
  source         = "./modules/databases"
  cluster_name   = var.cluster_name
  vpc_id         = module.networking.vpc_id
  vpc_cidr_block = module.networking.vpc_cidr_block
  # DB remains in private subnets for safety
  private_subnets = module.networking.private_subnet_ids
  db_name         = var.db_name
  db_username     = var.db_username
  db_password     = var.db_password
  environment     = var.environment
}

# Storage Module (S3 + CloudFront)
module "storage" {
  source      = "./modules/storage"
  s3_buckets  = var.s3_buckets
  environment = var.environment
}

# Container Registry Module (ECR)
module "container_registry" {
  source      = "./modules/container_registry"
  services    = var.services
  environment = var.environment
}

# Hosting Module (Amplify)
module "hosting" {
  source               = "./modules/hosting"
  cluster_name         = var.cluster_name
  amplify_repository   = var.amplify_repository
  amplify_access_token = var.amplify_access_token
  environment          = var.environment
}

# =============================================================================
# Kubernetes and Helm Provider Configuration
# =============================================================================

# Wait for EKS cluster to be ready and DNS to propagate (prevents 'no such host' errors)
resource "time_sleep" "wait_for_cluster" {
  depends_on      = [module.compute]
  create_duration = "60s"
}

# Fetch cluster details dynamically to ensure the most up-to-date endpoint
data "aws_eks_cluster" "cluster" {
  name = module.compute.cluster_name
  # Ensure we wait for the cluster to be ready before fetching data
  depends_on = [module.compute]
}

# Kubernetes Provider
provider "kubernetes" {
  host                   = data.aws_eks_cluster.cluster.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.cluster.certificate_authority[0].data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.compute.cluster_name]
  }
}

# Helm Provider
provider "helm" {
  kubernetes {
    host                   = data.aws_eks_cluster.cluster.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.cluster.certificate_authority[0].data)

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.compute.cluster_name]
    }
  }
}

# Kubectl Provider - Robust handling for CRDs
provider "kubectl" {
  apply_retry_count      = 5
  host                   = data.aws_eks_cluster.cluster.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.cluster.certificate_authority[0].data)
  load_config_file       = false

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.compute.cluster_name]
  }
}

# =============================================================================
# AWS Load Balancer Controller Installation
# =============================================================================

# AWS Load Balancer Controller Helm Release
resource "helm_release" "aws_lb_controller" {
  namespace  = "kube-system"
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = "1.9.1"
  wait       = true # Wait for LB controller to be fully ready
  timeout    = 600

  # Ensure nodes exist first and cluster is reachable
  depends_on = [
    module.compute,
    time_sleep.wait_for_cluster
  ]

  values = [
    <<-EOT
    clusterName: ${module.compute.cluster_name}
    serviceAccount:
      create: true
      name: aws-load-balancer-controller
      annotations:
        eks.amazonaws.com/role-arn: ${module.compute.lb_controller_irsa_role_arn}
    region: ${var.aws_region}
    vpcId: ${module.networking.vpc_id}
    EOT
  ]
}

# Add a 60-second delay to ensure the LB controller's webhook service
# actually has endpoints ready before other resources try to use it.
resource "time_sleep" "wait_for_lb_webhook" {
  depends_on      = [helm_release.aws_lb_controller]
  create_duration = "60s"
}

# =============================================================================
# Karpenter Installation and Configuration
# =============================================================================

# Karpenter Helm Release
resource "helm_release" "karpenter" {
  namespace  = "kube-system"
  name       = "karpenter"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = "1.0.6"
  wait       = true # Wait for Karpenter to be ready
  timeout    = 600

  # Ensure nodes exist, cluster is reachable, and LB controller webhook is ready
  depends_on = [
    module.compute,
    time_sleep.wait_for_cluster,
    time_sleep.wait_for_lb_webhook
  ]

  values = [
    <<-EOT
    replicas: 1
    dnsPolicy: Default
    serviceAccount:
      name: karpenter
      annotations:
        eks.amazonaws.com/role-arn: ${module.compute.karpenter_irsa_role_arn}
    controller:
      webhook:
        enabled: false
      resources:
        requests:
          cpu: 100m
          memory: 256Mi
        limits:
          cpu: 500m
          memory: 512Mi
    core:
      webhook:
        enabled: false
    settings:
      clusterName: ${module.compute.cluster_name}
      clusterEndpoint: ${data.aws_eks_cluster.cluster.endpoint}
      interruptionQueue: ${module.compute.karpenter_queue_name}
    EOT
  ]
}

# Karpenter EC2NodeClass
resource "kubectl_manifest" "karpenter_node_class" {
  yaml_body = yamlencode({
    apiVersion = "karpenter.k8s.aws/v1"
    kind       = "EC2NodeClass"
    metadata = {
      name = "default"
    }
    spec = {
      amiFamily                = "AL2023"
      amiSelectorTerms = [
        {
          alias = "al2023@latest"
        }
      ]
      role                     = module.compute.karpenter_node_iam_role_name
      associatePublicIPAddress = true
      subnetSelectorTerms = [
        {
          tags = {
            "kubernetes.io/role/elb" = "1"
          }
        }
      ]
      securityGroupSelectorTerms = [
        {
          id = module.compute.cluster_security_group_id
        }
      ]
      tags = {
        "karpenter.sh/discovery" = module.compute.cluster_name
      }
    }
  })

  depends_on = [helm_release.karpenter]
}

# Karpenter NodePool - defines which instances to launch
resource "kubectl_manifest" "karpenter_node_pool" {
  yaml_body = yamlencode({
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata = {
      name = "default"
    }
    spec = {
      template = {
        spec = {
          nodeClassRef = {
            group = "karpenter.k8s.aws"
            kind  = "EC2NodeClass"
            name  = "default"
          }
          requirements = [
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["spot"] },
            { key = "kubernetes.io/arch", operator = "In", values = ["arm64"] },
            { key = "karpenter.k8s.aws/instance-family", operator = "In", values = ["t4g"] },
            { key = "karpenter.k8s.aws/instance-size", operator = "In", values = ["micro"] }
          ]
        }
      }
      limits = {
        cpu    = 10
        memory = "10Gi"
      }
      disruption = {
        consolidationPolicy = "WhenEmptyOrUnderutilized"
        consolidateAfter    = "1m"
      }
    }
  })

  depends_on = [helm_release.karpenter]
}
