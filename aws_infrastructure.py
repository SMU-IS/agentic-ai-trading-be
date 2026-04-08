# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "diagrams",
# ]
# ///

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import EC2, EKS, AutoScaling, EC2ContainerRegistry
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
    "pad": "2.0",
    "nodesep": "1.2",
    "ranksep": "1.8",
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

    # --- Replica VPC ---
    with Cluster("Replica VPC (us-west-2 / DR)", graph_attr=cluster_attr):
        with Cluster("Public Subnets (Standby)"):
            nlb_dr = ELB("NLB\n(Standby)")
            kong_dr = Kong("Kong Ingress\n(Warm Standby)")
            eks_dr = EKS("EKS Cluster\n(Warm Standby)")

        with Cluster("Private Subnets (Data Sync)"):
            rds_dr = RDS("RDS Read Replica\n(DR Instance)")

    # --- Managed Storage (outside VPC) ---
    with Cluster("Managed Storage Services", graph_attr=cluster_attr):
        s3_primary = S3("S3 Storage\n(Primary us-east-1)")
        s3_replica = S3("S3 Storage\n(Replica us-west-2)")

    # --- Observability ---
    with Cluster("Observability & Monitoring", graph_attr=cluster_attr):
        prometheus = AmazonManagedPrometheus(
            "Amazon Managed Service\nfor Prometheus (AMP)"
        )
        cloudwatch = Cloudwatch("CloudWatch\n(Logs & Alarms)")
        grafana = AmazonManagedGrafana("Amazon Managed\nGrafana (AMG)")

    # --- Edges ---

    # 1. Global Entry & Security
    (
        dns
        >> Edge(color=COLOR_PRIMARY, label=" agentic-m.com / api.agentic-m.com")
        >> waf
        >> cloudfront
    )

    # 2. Frontend Delivery
    cloudfront >> Edge(color=COLOR_PRIMARY, label=" Static Content") >> amplify

    # 3. Primary API Path
    cloudfront >> Edge(color=COLOR_PRIMARY, label=" API Requests") >> igw >> nlb
    nlb >> Edge(color=COLOR_PRIMARY) >> kong
    kong >> Edge(color=COLOR_ACCENT, label=" ClusterIP / Policy") >> app_nodes

    # 4. Internal & Mesh Communication
    (
        app_nodes
        >> Edge(color=COLOR_ACCENT, style="dashed", label=" Service-to-Service")
        >> app_nodes
    )
    app_nodes >> Edge(color=COLOR_SECONDARY, style="dashed", label=" Secure TCP") >> rds
    (
        app_nodes
        >> Edge(color=COLOR_SECONDARY, style="dotted", label=" Private Endpoint")
        >> s3_primary
    )

    # 5. Replication & DR
    (
        rds
        >> Edge(color=COLOR_ACCENT, style="dashed", label=" Cross-Region Replication")
        >> rds_dr
    )
    (
        s3_primary
        >> Edge(color=COLOR_SECONDARY, style="dotted", label=" S3 CRR (Global)")
        >> s3_replica
    )

    # 6. Failover Path
    (
        cloudfront
        >> Edge(color=COLOR_SECONDARY, style="dashed", label=" Failover (Origin Group)")
        >> nlb_dr
    )
    nlb_dr >> Edge(color=COLOR_SECONDARY, style="dashed") >> kong_dr >> eks_dr

    # 7. Cluster Management
    karpenter >> Edge(color=COLOR_ACCENT, style="dashed") >> app_nodes
    (
        ecr
        >> Edge(color=COLOR_SECONDARY, style="dotted", label=" Pull (Provisioning)")
        >> app_nodes
    )

    # 8. Observability
    (
        app_nodes
        >> Edge(color=COLOR_SECONDARY, style="dashed", label=" Metrics (Remote Write)")
        >> prometheus
    )
    (
        app_nodes
        >> Edge(color=COLOR_SECONDARY, style="dashed", label=" Logs (FluentBit)")
        >> cloudwatch
    )
    prometheus >> Edge(color=COLOR_PRIMARY) >> grafana
    cloudwatch >> Edge(color=COLOR_PRIMARY) >> grafana
