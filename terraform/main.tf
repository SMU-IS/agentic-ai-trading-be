# =============================================================================
# Infrastructure-Centric Module Structure
# =============================================================================
# networking     - VPC, subnets, NAT gateways, routing
# compute        - EKS cluster, node groups
# databases      - RDS, database subnet groups, security groups
# storage        - S3 buckets, CloudFront CDN
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

# Compute Module (EKS)
module "compute" {
  source       = "./modules/compute"
  cluster_name = var.cluster_name
  vpc_id       = module.networking.vpc_id
  subnet_ids   = module.networking.private_subnet_ids
  environment  = var.environment
}

# Databases Module
module "databases" {
  source          = "./modules/databases"
  cluster_name    = var.cluster_name
  vpc_id          = module.networking.vpc_id
  vpc_cidr_block  = module.networking.vpc_cidr_block
  private_subnets = module.networking.private_subnets
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

# EKS Cluster Authentication
data "aws_eks_cluster_auth" "cluster" {
  name = module.compute.cluster_name
}

# Kubernetes Provider
provider "kubernetes" {
  host                   = module.compute.cluster_endpoint
  cluster_ca_certificate = base64decode(module.compute.cluster_certificate_authority_data)
  token                  = data.aws_eks_cluster_auth.cluster.token
}

# Helm Provider
provider "helm" {
  kubernetes {
    host                   = module.compute.cluster_endpoint
    cluster_ca_certificate = base64decode(module.compute.cluster_certificate_authority_data)
    token                  = data.aws_eks_cluster_auth.cluster.token
  }
}
