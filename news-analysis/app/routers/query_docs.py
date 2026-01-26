import logging

from app.schemas.query_docs_payload import QueryDocsRequest
from app.services._06_vectorisation import VectorisationService
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.post("/query", tags=["Retrieval"])
async def search_news(
    payload: QueryDocsRequest,
    service: VectorisationService = Depends(VectorisationService),
):
    """
    Search for articles in Qdrant based on semantic similarity.
    """

    logging.info("printed")

    try:
        results = await service.query_docs(
            query=payload.q, limit=payload.limit, score_threshold=payload.threshold
        )
        if not results:
            return {"message": "No relevant documents found.", "results": []}

        return {"status": "success", "count": len(results), "results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
