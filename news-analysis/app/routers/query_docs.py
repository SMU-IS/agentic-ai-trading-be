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
