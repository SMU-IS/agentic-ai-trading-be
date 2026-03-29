from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timedelta, timezone
from app.core.constant import APIPath
from app.services.scraper_controller import scraper_controller
from app.services.reddit_metrics import RedditMetricsService

router = APIRouter(tags=["Scraper Control"])


@router.post(APIPath.SCRAPER_START)
async def start_scraper(request: Request):
    try:
        return await scraper_controller.start(request.app)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(APIPath.SCRAPER_STOP)
async def stop_scraper(request: Request):
    try:
        return await scraper_controller.stop(request.app)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(APIPath.SCRAPER_STATUS)
async def scraper_status():
    try:
        return scraper_controller.status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get(APIPath.SCRAPER_METRICS)
async def reddit_metrics(request: Request):
    redis_client = request.app.state.redis_client
    metrics = RedditMetricsService(redis_client)

    return {
        "total_posts_daily": metrics.get_posts_last_day(),
        "avg_latency": metrics.get_avg_latency(),
        "avg_latency_daily": metrics.get_avg_latency_1d()
    }

