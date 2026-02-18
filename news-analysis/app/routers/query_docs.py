from app.schemas.query_docs_payload import QueryDocsRequest
from app.services.query_qdrant import QueryQdrant
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.post("/query", tags=["Retrieval"])
async def search_news(
    payload: QueryDocsRequest,
    service: QueryQdrant = Depends(QueryQdrant),
):
    try:
        results = await service.retrieve_ticker_insights(payload)
        if not results:
            return {"message": "No relevant documents found.", "results": []}

        return {"status": "success", "count": len(results), "results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ticker-events", tags=["Retrieval"])
async def get_ticker_events(
    ticker: str,
    event_type: str,
    limit: int = 10,
    service: QueryQdrant = Depends(QueryQdrant),
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
