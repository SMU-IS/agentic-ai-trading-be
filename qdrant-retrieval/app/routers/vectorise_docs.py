from fastapi import APIRouter, Depends, HTTPException

from app.core.constant import APIPath
from app.schemas.raw_news_payload import SourcePayload
from app.services.vectorisation import VectorisationService

router = APIRouter(tags=["Ingest Documents"])


@router.post(APIPath.VECTORISE)
async def vectorise(
    payload: SourcePayload,
    service: VectorisationService = Depends(VectorisationService),
):
    try:
        await service.ensure_indexes()
        result = await service.get_sanitised_news_payload(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
