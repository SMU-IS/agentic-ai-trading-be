from datetime import datetime, timedelta, timezone

import aiohttp
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from app.core.config import env_config


class AMPQueryClient:
    def __init__(self):
        self.session = boto3.Session(
            aws_access_key_id=env_config.aws_access_key_id,
            aws_secret_access_key=env_config.aws_secret_access_key,
            region_name=env_config.aws_region,
        )
        self.region = env_config.aws_region
        self.endpoint = env_config.prometheus_url

    async def query(self, query_str: str, time: datetime = None):
        if not self.endpoint:
            return None

        params = {"query": query_str}
        if time:
            params["time"] = time.timestamp()

        url = f"{self.endpoint.rstrip('/')}/api/v1/query"
        request = AWSRequest(method="GET", url=url, params=params)
        SigV4Auth(self.session.get_credentials(), "aps", self.region).add_auth(request)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url, params=params, headers=dict(request.headers)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        print(f"AMP Query failed: {resp.status} - {await resp.text()}")
                        return None
            except Exception as e:
                print(f"AMP Query error: {e}")
                return None


cw_client = boto3.client(
    "cloudwatch",
    aws_access_key_id=env_config.aws_access_key_id,
    aws_secret_access_key=env_config.aws_secret_access_key,
    region_name=env_config.aws_region,
)


async def get_cluster_uptime_from_cw():
    """
    Calculates uptime by checking the ratio of healthy vs total targets in the Load Balancer.
    If 0 hosts are healthy during a period, that period is considered 'down'.
    """
    if not env_config.load_balancer_name:
        return 0.0

    now = datetime.now(timezone.utc)
    start_time = now - timedelta(hours=24)

    try:
        # Query HealthyHostCount and UnHealthyHostCount
        # Note: Dimensions for NLB (NetworkELB) usually require TargetGroup and LoadBalancer
        # For simplicity, we try to fetch by LoadBalancer dimension if possible
        response = cw_client.get_metric_data(
            MetricDataQueries=[
                {
                    "Id": "healthy",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/NetworkELB",
                            "MetricName": "HealthyHostCount",
                            "Dimensions": [
                                {
                                    "Name": "LoadBalancer",
                                    "Value": env_config.load_balancer_name,
                                }
                            ],
                        },
                        "Period": 300,
                        "Stat": "Average",
                    },
                },
                {
                    "Id": "unhealthy",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/NetworkELB",
                            "MetricName": "UnHealthyHostCount",
                            "Dimensions": [
                                {
                                    "Name": "LoadBalancer",
                                    "Value": env_config.load_balancer_name,
                                }
                            ],
                        },
                        "Period": 300,
                        "Stat": "Average",
                    },
                },
            ],
            StartTime=start_time,
            EndTime=now,
        )

        healthy_values = response["MetricDataResults"][0]["Values"]
        unhealthy_values = response["MetricDataResults"][1]["Values"]

        if not healthy_values:
            return 0.0

        total_data_points = len(healthy_values)
        uptime_points = 0

        for h, u in zip(healthy_values, unhealthy_values or [0] * total_data_points):
            if h > 0:  # At least one host is healthy
                uptime_points += 1

        uptime_pct = (uptime_points / total_data_points) * 100
        return round(uptime_pct, 2)

    except Exception as e:
        print(f"CloudWatch Uptime Query failed: {e}")
        return 0.0


async def get_cluster_metrics():
    client = AMPQueryClient()

    # 1. Uptime Percentage (over last 24h)
    # We use a more robust 'at least one node up' logic to represent cluster availability.
    # This prevents node rotations or short-lived pods from dragging down the average.
    uptime_queries = [
        'avg_over_time(clamp_max(sum(up{job="kubernetes-nodes"}), 1)[24h:1m]) * 100',
        'avg_over_time(clamp_max(sum(up), 1)[24h:1m]) * 100',
        'avg(avg_over_time(up{job="kubernetes-nodes"}[24h])) * 100',
    ]

    uptime = 0.0
    for q in uptime_queries:
        uptime_data = await client.query(q)
        if uptime_data and uptime_data.get("data", {}).get("result"):
            try:
                uptime = float(uptime_data["data"]["result"][0]["value"][1])
                if uptime > 0:
                    break
            except (IndexError, ValueError):
                continue

    if uptime == 0.0:
        uptime = await get_cluster_uptime_from_cw()

    # 2. Average Latency (over last 1h)
    latency_queries = [
        "avg(rate(kong_http_request_duration_seconds_sum[1h]) / rate(kong_http_request_duration_seconds_count[1h]))",
        "avg(rate(nginx_ingress_controller_request_duration_seconds_sum[1h]) / rate(nginx_ingress_controller_request_duration_seconds_count[1h]))",
        "avg(rate(http_request_duration_seconds_sum[1h]) / rate(http_request_duration_seconds_count[1h]))",
    ]

    latency_ms = 0.0
    for q in latency_queries:
        latency_data = await client.query(q)
        if (
            latency_data
            and latency_data.get("data", {}).get("result")
            and latency_data["data"]["result"]
        ):
            try:
                latency_ms = float(latency_data["data"]["result"][0]["value"][1]) * 1000
                if latency_ms > 0:
                    break
            except (IndexError, ValueError):
                continue

    return {
        "uptime_percentage": round(uptime, 2),
        "average_latency_ms": round(latency_ms, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
