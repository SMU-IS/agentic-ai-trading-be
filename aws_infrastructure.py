# /// script
# dependencies = ["diagrams"]
# ///
import os
import re
import subprocess
import sys

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR, EKS, AutoScaling, EC2Instance, EC2Instances
from diagrams.aws.database import RDSPostgresqlInstance
from diagrams.aws.management import (
    AmazonManagedGrafana,
    AmazonManagedPrometheus,
    Cloudwatch,
)
from diagrams.aws.mobile import Amplify
from diagrams.aws.network import (
    CloudFront,
    ElbNetworkLoadBalancer,
    InternetGateway,
    Route53,
)
from diagrams.aws.security import WAF, SecretsManager
from diagrams.aws.storage import S3
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.vcs import Github

OUT = "aws_infrastructure"

graph_attr = {
    "rankdir": "LR",
    "fontsize": "20",
    "fontname": "Helvetica Neue",
    "pad": "3.5",
    "nodesep": "0.8",
    "ranksep": "2.2",
    "bgcolor": "white",
    "splines": "ortho",
    "label": "Agent M  —  High-Availability Multi-Region Architecture (us-east-1 Primary)\n\n────── Primary flow          - - - - - - - - -  Failover / Admin / Replication\n\n",
    "labelloc": "b",
    "labeljust": "l",
    "fontcolor": "#333333",
    "dpi": "96",
    "compound": "true",
}

node_attr = {"fontsize": "13", "fontname": "Helvetica Neue"}

# ── Step 1: Generate DOT + PNG ────────────────────────────────────────────────
with Diagram(
    "",
    show=False,
    filename=OUT,
    outformat=["png", "dot"],
    graph_attr=graph_attr,
    node_attr=node_attr,
):
    with Cluster("CI/CD Pipeline"):
        github_repo = Github("GitHub Repo")
        gh_actions = GithubActions("GitHub Actions")
        ecr = ECR("Amazon ECR")
        github_repo >> gh_actions

    with Cluster("Global Edge Services"):
        r53 = Route53("Route 53\nagentic-m.com")
        waf = WAF("AWS WAF")
        cf = CloudFront("CloudFront")
        amplify = Amplify("AWS Amplify")
        r53 >> waf >> cf
        r53 >> amplify

    with Cluster("Security"):
        secrets = SecretsManager("Secrets Manager")

    with Cluster("Primary VPC — us-east-1"):
        with Cluster(" "):
            igw_p = InternetGateway("Internet Gateway")
            nlb_p = ElbNetworkLoadBalancer("NLB")
            kong_p = EKS("Kong Ingress")
            karpenter = AutoScaling("Karpenter")
            app_pods = EC2Instances("App Pods (HPA)")
            igw_p >> nlb_p >> kong_p >> karpenter >> app_pods
        with Cluster("  "):
            bastion_p = EC2Instance("Bastion Host")
            rds_p = RDSPostgresqlInstance("RDS PostgreSQL\nMulti-AZ")
            bastion_p >> Edge(style="dashed") >> rds_p

    with Cluster("Replica VPC — us-west-2 (DR)"):
        with Cluster("   "):
            igw_dr = InternetGateway("Internet Gateway")
            nlb_dr = ElbNetworkLoadBalancer("NLB (DR)")
            kong_dr = EKS("Kong Ingress\nWarm Standby")
            app_dr = EC2Instances("App Pods (DR)")
            igw_dr >> nlb_dr >> kong_dr >> app_dr
        with Cluster("    "):
            bastion_dr = EC2Instance("Bastion Host (DR)")
            rds_dr = RDSPostgresqlInstance("RDS Read\nReplica (DR)")
            bastion_dr >> Edge(style="dashed") >> rds_dr

    with Cluster("Managed Storage"):
        s3_p = S3("S3 Primary\nus-east-1")
        s3_dr = S3("S3 Replica\nus-west-2")
        s3_p >> Edge(label="  Cross-Region Replication  ") >> s3_dr

    with Cluster("Observability"):
        amp = AmazonManagedPrometheus("AMP")
        cw = Cloudwatch("CloudWatch")
        grafana = AmazonManagedGrafana("Managed Grafana")
        [amp, cw] >> grafana

    inv = Edge(style="invis")
    ecr >> inv >> cf
    cf >> inv >> igw_p
    igw_p >> inv >> igw_dr
    app_pods >> inv >> s3_p
    s3_p >> inv >> amp
    cf >> inv >> secrets

    gh_actions >> ecr >> kong_p
    gh_actions >> amplify
    cf >> Edge(label="\n\n\nPrimary Traffic\n\n\n") >> igw_p
    cf >> Edge(style="dashed") >> igw_dr
    secrets >> kong_p
    secrets >> Edge(style="dashed") >> kong_dr
    rds_p >> Edge(style="dashed", label="  Replication  ") >> rds_dr
    app_pods >> s3_p
    app_dr >> Edge(style="dashed") >> s3_dr
    app_pods >> amp
    app_pods >> cw
    app_dr >> Edge(style="dashed") >> amp
    app_dr >> Edge(style="dashed") >> cw

# ── Step 2: Patch DOT — cluster labels to top ─────────────────────────────────
with open(f"{OUT}.dot") as f:
    dot = f.read()

dot = re.sub(r'\s*bb="[^"]*",', "", dot)
dot = re.sub(r'\s*lp="[^"]*",', "", dot)
dot = re.sub(r"\s*lheight=[^,\n]+,", "", dot)
dot = re.sub(r"\s*lwidth=[^,\n]+,", "", dot)


def patch_clusters(dot):
    lines, in_cluster = [], False
    for line in dot.split("\n"):
        if re.match(r'\s*subgraph (?:cluster_|"cluster_)', line):
            in_cluster = True
        if in_cluster and re.match(r"\s*graph \[", line):
            lines += [line, "\t\t\tlabelloc=t,", "\t\t\tmargin=30,"]
            in_cluster = False
            continue
        lines.append(line)
    return "\n".join(lines)


dot = patch_clusters(dot)

with open("/tmp/patched.dot", "w") as f:
    f.write(dot)

# ── Step 3: Render final PNG ──────────────────────────────────────────────────
r = subprocess.run(
    ["dot", "-Tpng", "-Gdpi=96", "/tmp/patched.dot", "-o", f"{OUT}.png"],
    capture_output=True,
    text=True,
)
print(r.stderr[:200] if r.returncode != 0 else f"Diagram saved to {OUT}.png")
