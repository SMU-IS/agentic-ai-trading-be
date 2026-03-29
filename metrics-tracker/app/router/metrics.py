import json

from fastapi import APIRouter, HTTPException

from app.services.pipeline_metrics import (
    compute_pipeline_metrics,
    redis_client,
    FUNNEL_SNAPSHOT_KEY,
    SERVICE_SNAPSHOT_KEY,
)

router = APIRouter(prefix="/metrics")


@router.get("/pipeline")
async def get_pipeline_funnel():
    data = await redis_client.get(FUNNEL_SNAPSHOT_KEY)
    if not data:
        raise HTTPException(status_code=404, detail="No snapshot yet — aggregator may still be starting up")
    return json.loads(data)


@router.get("/services")
async def get_service_metrics():
    data = await redis_client.get(SERVICE_SNAPSHOT_KEY)
    if not data:
        raise HTTPException(status_code=404, detail="No snapshot yet — aggregator may still be starting up")
    return json.loads(data)


@router.post("/refresh")
async def refresh_pipeline_metrics():
    await compute_pipeline_metrics()
    funnel   = await redis_client.get(FUNNEL_SNAPSHOT_KEY)
    services = await redis_client.get(SERVICE_SNAPSHOT_KEY)
    return {
        "pipeline": json.loads(funnel),
        "services": json.loads(services),
    }
