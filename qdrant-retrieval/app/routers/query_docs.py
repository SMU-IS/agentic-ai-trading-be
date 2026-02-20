from fastapi import APIRouter, Depends, HTTPException

from app.core.constant import APIPath
from app.schemas.query_docs_payload import QueryDocsRequest
from app.services.query_qdrant import QueryQdrantService

router = APIRouter(tags=["Query Documents"])


@router.post(APIPath.QUERY)
async def search_news(
    payload: QueryDocsRequest,
    service: QueryQdrantService = Depends(QueryQdrantService),
):
    try:
        results = await service.retrieve_ticker_insights(payload)
        if not results:
            return {"message": "No relevant documents found.", "results": []}

        return {"status": "success", "count": len(results), "results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(APIPath.TICKER_EVENTS)
async def get_ticker_events(
    ticker: str,
    event_type: str,
    limit: int = 10,
    service: QueryQdrantService = Depends(QueryQdrantService),
):
    try:
        results = service.retrieved_filtered_ticker_events(
            ticker=ticker, event_type=event_type, limit=limit
        )
        if not results:
            return {"message": "No relevant documents found.", "results": []}

        return {"status": "success", "count": len(results), "results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
