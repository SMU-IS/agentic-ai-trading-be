from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from app.core.constant import APIPath
from app.services.scraper_controller import scraper_controller

router = APIRouter(tags=["Scraper Control"])


@router.post(APIPath.SCRAPER_START)
async def start_scraper(
    request: Request,
    mode: Optional[str] = Query(
        default=None,
        description="Override scraper mode: 'batch' or 'stream'. Defaults to MODE env var.",
    ),
):
    """Start the scraper. Pass ?mode=stream to force streaming mode."""
    try:
        return await scraper_controller.start(request.app, mode=mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scraper/stream/start")
async def start_stream_scraper(request: Request):
    """Convenience endpoint: start the scraper in streaming mode."""
    try:
        return await scraper_controller.start(request.app, mode="stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scraper/stream/stop")
async def stop_stream_scraper(request: Request):
    """Convenience endpoint: stop a running stream scraper."""
    try:
        return await scraper_controller.stop(request.app)
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