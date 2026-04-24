# /// script
# dependencies = ["diagrams"]
# ///
import re
import subprocess

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
    "pad": "2.5",
    "nodesep": "0.6",
    "ranksep": "1.8",
    "bgcolor": "white",
    "splines": "ortho",
    "label": (
        "Agent M  —  High-Availability Multi-AZ Architecture (us-east-1)\n\n"
        "──────  Solid: Active Path / Synchronous Request Flow\n"
        "- - - - -  Dashed: Standby Path / Asynchronous Replication & Failover\n"
        "· · · · ·  Dotted: Management Plane / Governance & Security Access\n\n"
    ),
    "labelloc": "b",
    "labeljust": "l",
    "fontcolor": "#333333",
    "dpi": "96",
    "compound": "true",
}

node_attr = {"fontsize": "13", "fontname": "Helvetica Neue"}

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

    with Cluster("VPC — us-east-1"):
        # Positioned outside and ON TOP of the subnets
        igw = InternetGateway("Internet Gateway")

        with Cluster("Public Subnets (Multi-AZ)"):
            nlb = ElbNetworkLoadBalancer("NLB")
            bastion = EC2Instance("Bastion Host")

        # Removed the horizontal anchor to allow vertical positioning in LR layout

        with Cluster("Scalable EKS Cluster (Multi-AZ)"):
            kong = EKS("Kong Ingress")
            karpenter = AutoScaling("Karpenter\nAuto-Scaling")
            app_pods = EC2Instances("App Pods (HPA)")
            kong >> karpenter >> app_pods

        with Cluster("Private Subnets (Multi-AZ)"):
            rds_primary = RDSPostgresqlInstance("RDS PostgreSQL\nPrimary (AZ-a)")
            rds_standby = RDSPostgresqlInstance("RDS PostgreSQL\nStandby (AZ-b)")
            (
                rds_primary
                >> Edge(style="dashed", label="  Sync Replication  ")
                >> rds_standby
            )

    with Cluster("Managed Storage"):
        s3 = S3("S3\nus-east-1")

    with Cluster("Observability"):
        amp = AmazonManagedPrometheus("AMP")
        cw = Cloudwatch("CloudWatch")
        grafana = AmazonManagedGrafana("Managed Grafana")
        [amp, cw] >> grafana

    # Alignment Spine
    inv = Edge(style="invis")
    ecr >> inv >> cf
    cf >> inv >> igw
    app_pods >> inv >> s3
    s3 >> inv >> amp
    cf >> inv >> secrets

    gh_actions >> ecr >> kong
    gh_actions >> amplify

    # Logical Ingress Flow (CloudFront -> NLB Origin)
    cf >> nlb
    nlb >> kong

    # Governance & Management
    bastion >> Edge(style="dotted") >> rds_primary
    secrets >> Edge(style="dotted") >> kong

    # App Logic
    app_pods >> Edge(style="dashed") >> s3
    app_pods >> amp
    app_pods >> cw

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
            lines += [line, "\t\t\tlabelloc=t,", "\t\t\tmargin=40,"]
            in_cluster = False
            continue
        lines.append(line)
    return "\n".join(lines)


dot = patch_clusters(dot)
with open("/tmp/patched.dot", "w") as f:
    f.write(dot)

r = subprocess.run(
    ["dot", "-Tpng", "-Gdpi=96", "/tmp/patched.dot", "-o", f"{OUT}.png"],
    capture_output=True,
    text=True,
)

if r.returncode != 0:
    print(f"Error rendering diagram: {r.stderr[:200]}")
else:
    print(f"Architecture diagram successfully generated: {OUT}.png")
