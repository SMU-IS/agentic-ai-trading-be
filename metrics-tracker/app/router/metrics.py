import json

from fastapi import APIRouter, HTTPException

from app.services.cluster_metrics import get_cluster_metrics
from app.services.pipeline_metrics import (
    FUNNEL_SNAPSHOT_KEY,
    SERVICE_SNAPSHOT_KEY,
    compute_pipeline_metrics,
    redis_client,
)

router = APIRouter()


@router.get("/pipeline")
async def get_pipeline_funnel():
    data = await redis_client.get(FUNNEL_SNAPSHOT_KEY)
    if not data:
        raise HTTPException(
            status_code=404,
            detail="No snapshot yet — aggregator may still be starting up",
        )
    return json.loads(data)


@router.get("/service")
async def get_service_metrics():
    data = await redis_client.get(SERVICE_SNAPSHOT_KEY)
    if not data:
        raise HTTPException(
            status_code=404,
            detail="No snapshot yet — aggregator may still be starting up",
        )
    return json.loads(data)


@router.get("/cluster")
async def get_cluster_status():
    """
    Returns the cluster uptime (percentage) and average latency from AMP/CloudWatch.
    """
    try:
        metrics = await get_cluster_metrics()
        return metrics
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch cluster metrics: {str(e)}"
        )


@router.post("/refresh")
async def refresh_pipeline_metrics():
    await compute_pipeline_metrics()
    funnel = await redis_client.get(FUNNEL_SNAPSHOT_KEY)
    service = await redis_client.get(SERVICE_SNAPSHOT_KEY)
    return {
        "pipeline": json.loads(funnel),
        "service": json.loads(service),
    }
