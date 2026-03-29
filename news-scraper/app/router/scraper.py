from app.core.constant import APIPath
from app.services.scraper_controller import scraper_controller
from fastapi import APIRouter, HTTPException, Request

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
