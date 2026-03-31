# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "diagrams",
# ]
# ///

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import EC2, EKS, AutoScaling, EC2ContainerRegistry
from diagrams.aws.database import RDS
from diagrams.aws.management import AmazonManagedGrafana, AmazonManagedPrometheus, Cloudwatch
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
    "pad": "0.5",
    "nodesep": "0.8",
    "ranksep": "1.0",
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
    "Agent M AWS Infrastructure",
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

    # --- Primary VPC ---
    with Cluster("Primary VPC (us-east-1)", graph_attr=cluster_attr):
        igw = InternetGateway("Internet Gateway")

        with Cluster("Public Subnets", graph_attr=cluster_attr):
            nlb = ELB("NLB\n(Internet-Facing)")

            with Cluster("Scalable EKS Cluster", graph_attr=cluster_attr):
                eks_master = EKS("EKS Control Plane")
                kong = Kong("Kong Ingress\n(HA Configuration)")

                with Cluster("Auto-Scaling Node Fleet"):
                    app_nodes = EC2("Scalable App Pods\n(HPA / Spot)")
                    karpenter = AutoScaling("Karpenter\n(Elastic Scaling)")

        with Cluster("Private Subnets", graph_attr=cluster_attr):
            rds = RDS("RDS PostgreSQL\n(Multi-AZ Master)")

    # --- Replica VPC (Simulation) ---
    with Cluster("Replica VPC (us-west-2 / DR)", graph_attr=cluster_attr):
        with Cluster("Public Subnets (Standby)"):
            nlb_dr = ELB("NLB\n(Standby)")
            eks_dr = EKS("EKS Cluster\n(Warm Standby)")

        with Cluster("Private Subnets (Data Sync)"):
            rds_dr = RDS("RDS Read Replica\n(DR Instance)")

    s3 = S3("S3 Buckets\n(Replicated Store)")

    with Cluster("Observability & Monitoring", graph_attr=cluster_attr):
        prometheus = AmazonManagedPrometheus("AWS Prometheus\n(Metrics Store)")
        cloudwatch = Cloudwatch("CloudWatch\n(Logs & Alarms)")
        grafana = AmazonManagedGrafana("AWS Grafana\n(Visualizations)")

    # --- Precise Route & Logical Connections ---

    # 1. Frontend Route
    dns >> Edge(color=COLOR_PRIMARY, label=" Main Domain") >> amplify

    # 2. API Route (The specified path)
    dns >> Edge(color=COLOR_PRIMARY, label=" api. Subdomain") >> cloudfront
    cloudfront >> Edge(color=COLOR_PRIMARY, label=" Primary Path") >> igw >> nlb
    nlb >> Edge(color=COLOR_PRIMARY) >> kong
    kong >> Edge(color=COLOR_ACCENT, label=" ClusterIP / Policy") >> app_nodes

    # 3. Internal & Mesh Communication
    (
        app_nodes
        >> Edge(color=COLOR_ACCENT, style="dashed", label=" Service-to-Service")
        >> app_nodes
    )
    app_nodes >> Edge(color=COLOR_SECONDARY, style="dashed", label=" Secure TCP") >> rds
    app_nodes >> Edge(color=COLOR_SECONDARY, style="dotted") >> s3

    # 4. Replication & DR Logical Flow
    (
        rds
        >> Edge(color=COLOR_ACCENT, style="dashed", label=" Cross-Region Replication")
        >> rds_dr
    )
    s3 >> Edge(color=COLOR_SECONDARY, style="dotted", label=" Replication") >> s3

    # 5. Failover Path (Optional Visibility)
    (
        cloudfront
        >> Edge(color=COLOR_SECONDARY, style="dashed", label=" Failover Path")
        >> nlb_dr
    )

    # 6. Cluster Management
    karpenter >> Edge(color=COLOR_ACCENT, style="dashed") >> app_nodes
    ecr >> Edge(color=COLOR_SECONDARY, style="dotted", label=" Pull") >> app_nodes

    # 7. Observability Flow
    app_nodes >> Edge(color=COLOR_SECONDARY, style="dashed", label=" Export Metrics") >> prometheus
    app_nodes >> Edge(color=COLOR_SECONDARY, style="dashed", label=" Export Logs") >> cloudwatch
    prometheus >> Edge(color=COLOR_PRIMARY) >> grafana
    cloudwatch >> Edge(color=COLOR_PRIMARY) >> grafana
