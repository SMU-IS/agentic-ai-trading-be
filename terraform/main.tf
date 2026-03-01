# Networking (VPC)
module "vpc" {
  source          = "./modules/vpc"
  cluster_name    = var.cluster_name
  vpc_cidr        = "10.0.0.0/16"
  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
  environment     = var.environment
}

# EKS Cluster
module "eks" {
  source       = "./modules/eks"
  cluster_name = var.cluster_name
  vpc_id       = module.vpc.vpc_id
  subnet_ids   = module.vpc.private_subnets
  environment  = var.environment
}

# ECR Repositories Module
module "ecr" {
  source      = "./modules/ecr"
  services    = var.services
  environment = var.environment
}

# S3 Buckets and CDN Module
module "s3_cdn" {
  source      = "./modules/s3_cdn"
  s3_buckets  = var.s3_buckets
  environment = var.environment
}

# RDS Database Module
module "rds" {
  source          = "./modules/rds"
  cluster_name    = var.cluster_name
  vpc_id          = module.vpc.vpc_id
  vpc_cidr_block  = module.vpc.vpc_cidr_block
  private_subnets = module.vpc.private_subnets
  db_name         = var.db_name
  db_username     = var.db_username
  db_password     = var.db_password
  environment     = var.environment
}

# Amplify Frontend Module
module "amplify" {
  source               = "./modules/amplify"
  cluster_name         = var.cluster_name
  amplify_repository   = var.amplify_repository
  amplify_access_token = var.amplify_access_token
  environment          = var.environment
}

# Kubernetes and Helm Provider Data
data "aws_eks_cluster_auth" "cluster" {
  name = module.eks.cluster_name
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  token                  = data.aws_eks_cluster_auth.cluster.token
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    token                  = data.aws_eks_cluster_auth.cluster.token
  }
}
