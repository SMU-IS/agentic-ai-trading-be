# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "diagrams",
# ]
# ///

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import EC2, AutoScaling, EC2ContainerRegistry
from diagrams.aws.database import RDS
from diagrams.aws.management import (
    AmazonManagedGrafana,
    AmazonManagedPrometheus,
    Cloudwatch,
)
from diagrams.aws.mobile import Amplify
from diagrams.aws.network import (
    ELB,
    CloudFront,
    InternetGateway,
    Route53,
)
from diagrams.aws.security import WAF
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
    "splines": "ortho",
    "pad": "1.0",
    "nodesep": "0.6",
    "ranksep": "1.0",
    "fontname": "Helvetica",
    "rankdir": "LR",
}

node_attr = {
    "fontname": "Helvetica",
    "fontsize": "11",
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
    dns = Route53("Route 53\n(Global Traffic Mgr)")

    with Cluster("Global Edge Services"):
        waf = WAF("AWS WAF\n(Edge Security)")
        cloudfront = CloudFront("CloudFront\n(API Acceleration)")
        amplify = Amplify("AWS Amplify\n(Frontend Hosting)")
        ecr = EC2ContainerRegistry("ECR\n(Image Registry)")

    # --- Primary VPC ---
    with Cluster("Primary VPC (us-east-1)", graph_attr=cluster_attr):
        igw = InternetGateway("Internet Gateway")

        with Cluster("Public Subnets", graph_attr=cluster_attr):
            nlb = ELB("NLB\n(Internet-Facing)")

        with Cluster("Scalable EKS Cluster", graph_attr=cluster_attr):
            kong = Kong("Kong Ingress\n(HA Configuration)")
            with Cluster("Auto-Scaling Node Fleet"):
                karpenter = AutoScaling("Karpenter\n(Elastic Scaling)")
                app_nodes = EC2("Scalable App Pods\n(HPA / On-Demand)")

        with Cluster("Private Subnets", graph_attr=cluster_attr):
            rds = RDS("RDS PostgreSQL\n(Multi-AZ Master)")

    # --- Replica VPC (EXACT COPY) ---
    with Cluster("Replica VPC (us-west-2 / DR)", graph_attr=cluster_attr):
        igw_dr = InternetGateway("Internet Gateway (DR)")

        with Cluster("Public Subnets (DR)", graph_attr=cluster_attr):
            nlb_dr = ELB("NLB\n(Internet-Facing DR)")

        with Cluster("Scalable EKS Cluster (DR)", graph_attr=cluster_attr):
            kong_dr = Kong("Kong Ingress\n(Warm Standby)")
            with Cluster("Auto-Scaling Node Fleet (DR)"):
                karpenter_dr = AutoScaling("Karpenter\n(Elastic Scaling DR)")
                app_nodes_dr = EC2("Scalable App Pods\n(Warm Standby)")

        with Cluster("Private Subnets (DR)", graph_attr=cluster_attr):
            rds_dr = RDS("RDS Read Replica\n(DR Instance)")

    # --- Managed Storage ---
    with Cluster("Managed Storage Services", graph_attr=cluster_attr):
        s3_primary = S3("S3 Storage\n(Primary us-east-1)")
        s3_replica = S3("S3 Storage\n(Replica us-west-2)")

    # --- Observability ---
    with Cluster("Observability & Monitoring", graph_attr=cluster_attr):
        prometheus = AmazonManagedPrometheus("AMP")
        cloudwatch = Cloudwatch("CloudWatch")
        grafana = AmazonManagedGrafana("AMG")

    # --- Edges ---

    # 1. Global
    (
        dns
        >> Edge(color=COLOR_PRIMARY, label=" agentic-m.com / api.agentic-m.com")
        >> waf
        >> cloudfront
    )
    cloudfront >> Edge(color=COLOR_PRIMARY) >> amplify

    # 2. Primary Path
    (
        cloudfront
        >> Edge(color=COLOR_PRIMARY, label=" API")
        >> igw
        >> nlb
        >> kong
        >> app_nodes
    )
    app_nodes >> Edge(color=COLOR_SECONDARY, style="dashed") >> rds
    app_nodes >> Edge(color=COLOR_SECONDARY, style="dotted") >> s3_primary

    # 3. Failover Path (Constraint keeps DR VPC from jumping around)
    (
        cloudfront
        >> Edge(color=COLOR_SECONDARY, style="dashed", label=" Failover")
        >> igw_dr
        >> nlb_dr
        >> kong_dr
        >> app_nodes_dr
    )

    # 4. Replication
    rds >> Edge(color=COLOR_ACCENT, style="dashed") >> rds_dr
    s3_primary >> Edge(color=COLOR_SECONDARY, style="dotted") >> s3_replica

    # 5. Cluster Management (The FIX: constraint="false")
    karpenter >> Edge(color=COLOR_ACCENT, style="dashed") >> app_nodes
    (
        karpenter_dr
        >> Edge(color=COLOR_ACCENT, style="dashed", constraint="false")
        >> app_nodes_dr
    )

    ecr >> Edge(color=COLOR_SECONDARY, style="dotted", label=" Pull") >> app_nodes
    (
        ecr
        >> Edge(color=COLOR_SECONDARY, style="dotted", constraint="false")
        >> app_nodes_dr
    )

    # 6. Observability
    app_nodes >> Edge(color=COLOR_SECONDARY, style="dashed") >> [prometheus, cloudwatch]
    [prometheus, cloudwatch] >> grafana
