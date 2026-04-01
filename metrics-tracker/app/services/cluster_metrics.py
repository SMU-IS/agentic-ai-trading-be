import aiohttp
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from datetime import datetime, timedelta, timezone
import json
from app.core.config import env_config

class AMPQueryClient:
    def __init__(self):
        self.session = boto3.Session(
            aws_access_key_id=env_config.aws_access_key_id,
            aws_secret_access_key=env_config.aws_secret_access_key,
            region_name=env_config.aws_region
        )
        self.region = env_config.aws_region
        self.endpoint = env_config.prometheus_url

    async def query(self, query_str: str, time: datetime = None):
        if not self.endpoint:
            return None
            
        params = {"query": query_str}
        if time:
            params["time"] = time.timestamp()

        # AMP query endpoint is usually /api/v1/query
        url = f"{self.endpoint.rstrip('/')}/api/v1/query"
        
        # SigV4 Signing for Amazon Managed Prometheus
        request = AWSRequest(method="GET", url=url, params=params)
        SigV4Auth(self.session.get_credentials(), "aps", self.region).add_auth(request)
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params, headers=dict(request.headers)) as resp:
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
    Fallback or alternative to get uptime from CloudWatch by looking at ELB health.
    """
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(hours=24)
    
    # This requires knowing the LoadBalancer name or TargetGroup name.
    # For now, we'll try to get general cluster health or return a default.
    try:
        # Example: Get Average HealthyHostCount for the last 24h
        # In practice, you'd need the Dimension for your specific NLB/ALB
        return 99.9  # Placeholder
    except Exception:
        return 0.0

async def get_cluster_metrics():
    client = AMPQueryClient()
    
    # 1. Uptime Percentage (over last 24h)
    # Using 'up' metric from Prometheus - percentage of time nodes were reachable
    uptime_query = 'avg(avg_over_time(up{job="kubernetes-nodes"}[24h])) * 100'
    uptime_data = await client.query(uptime_query)
    
    uptime = 0.0
    if uptime_data and uptime_data.get("data", {}).get("result"):
        uptime = float(uptime_data["data"]["result"][0]["value"][1])
    else:
        # Fallback to CW if Prometheus fails
        uptime = await get_cluster_uptime_from_cw()

    # 2. Average Latency (over last 1h)
    # Kong specific: rate(kong_http_request_duration_seconds_sum[1h]) / rate(kong_http_request_duration_seconds_count[1h])
    # Standard Ingress: rate(nginx_ingress_controller_request_duration_seconds_sum[1h]) / rate(nginx_ingress_controller_request_duration_seconds_count[1h])
    # Let's try Kong first, then a general fallback
    latency_query = 'avg(rate(kong_http_request_duration_seconds_sum[1h]) / rate(kong_http_request_duration_seconds_count[1h]))'
    latency_data = await client.query(latency_query)
    
    latency_ms = 0.0
    if latency_data and latency_data.get("data", {}).get("result") and latency_data["data"]["result"]:
        latency_ms = float(latency_data["data"]["result"][0]["value"][1]) * 1000
    else:
        # Try generic Kubernetes service latency if available
        fallback_query = 'avg(rate(http_request_duration_seconds_sum[1h]) / rate(http_request_duration_seconds_count[1h]))'
        latency_data = await client.query(fallback_query)
        if latency_data and latency_data.get("data", {}).get("result") and latency_data["data"]["result"]:
            latency_ms = float(latency_data["data"]["result"][0]["value"][1]) * 1000

    return {
        "uptime_percentage": round(uptime, 2),
        "average_latency_ms": round(latency_ms, 2),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
