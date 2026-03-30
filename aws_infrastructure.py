# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "diagrams",
# ]
# ///

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import EC2, EKS, AutoScaling, EC2ContainerRegistry
from diagrams.aws.database import RDS
from diagrams.aws.mobile import Amplify
from diagrams.aws.network import (
    ELB,
    VPC,
    CloudFront,
    InternetGateway,
    PrivateSubnet,
    PublicSubnet,
    Route53,
)
from diagrams.aws.storage import S3
from diagrams.onprem.network import Kong

# Professional Minimalist Palette
COLOR_PRIMARY = "#2d3436"
COLOR_SECONDARY = "#636e72"
COLOR_ACCENT = "#0984E3"
BG_COLOR = "#ffffff"

graph_attr = {
    "fontsize": "32",
    "bgcolor": BG_COLOR,
    "splines": "polyline",
    "pad": "1.0",
    "nodesep": "1.5",
    "ranksep": "2.0",
    "fontname": "Helvetica",
}

node_attr = {
    "fontname": "Helvetica",
    "fontsize": "12",
}

cluster_attr = {
    "fontname": "Helvetica-Bold",
    "fontsize": "16",
    "style": "dashed",
    "color": COLOR_SECONDARY,
}

with Diagram(
    "AWS Infrastructure",
    show=False,
    filename="aws_infrastructure",
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
):
    # DNS & Global Layer
    dns = Route53("Route 53\n(agentic-m.com)")

    with Cluster("Global Edge Services"):
        amplify = Amplify("AWS Amplify\n(Frontend Hosting)")
        cloudfront = CloudFront("CloudFront\n(API Acceleration)")
        ecr = EC2ContainerRegistry("ECR\n(Image Registry)")

    with Cluster("VPC (10.0.0.0/16)", graph_attr=cluster_attr):
        igw = InternetGateway("Internet Gateway")

        with Cluster("Public Subnets (us-east-1a/b)", graph_attr=cluster_attr):
            nlb = ELB("NLB\n(Internet-Facing)")

            with Cluster("EKS: Compute Cluster (v1.35)", graph_attr=cluster_attr):
                eks_master = EKS("EKS Control Plane")
                kong = Kong("Kong Ingress\n(DB-less)")

                with Cluster("Node Fleet (Spot/Graviton)"):
                    system_nodes = EC2("System Nodes\n(t4g.small)")
                    app_nodes = EC2("App Pods\n(t4g.micro)")
                    karpenter = AutoScaling("Karpenter\n(Autoscaler)")

        with Cluster("Private Subnets (Isolated Data)", graph_attr=cluster_attr):
            rds = RDS("RDS PostgreSQL\n(db.t4g.micro)")

    s3 = S3("S3 Buckets\n(State/Metrics)")

    # --- Precise Route & Logical Connections ---

    # 1. Frontend Route
    dns >> Edge(color=COLOR_PRIMARY, label=" Main Domain") >> amplify

    # 2. API Route (The specified path)
    dns >> Edge(color=COLOR_PRIMARY, label=" api. Subdomain") >> cloudfront
    cloudfront >> Edge(color=COLOR_PRIMARY, label=" Origin Request") >> igw >> nlb
    nlb >> Edge(color=COLOR_PRIMARY) >> kong
    kong >> Edge(color=COLOR_ACCENT, label=" ClusterIP") >> app_nodes

    # 3. Data & Storage Access (Restricted to Private/Internal)
    app_nodes >> Edge(color=COLOR_SECONDARY, style="dashed", label=" Secure TCP") >> rds
    app_nodes >> Edge(color=COLOR_SECONDARY, style="dotted") >> s3

    # 4. Cluster Management
    karpenter >> Edge(color=COLOR_ACCENT, style="dashed") >> app_nodes
    ecr >> Edge(color=COLOR_SECONDARY, style="dotted", label=" Pull") >> app_nodes
    eks_master - system_nodes
