from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.constant import APIPath
from app.schemas.query_docs_payload import QueryDocsRequest
from app.services.query_qdrant import QueryQdrantService

router = APIRouter(tags=["Query Documents"])


# @router.get(APIPath.NEWS)
# async def get_all_news(
#     limit: int = Query(20, ge=1, le=100),
#     offset: str = Query(None, description="The offset ID for pagination"),
#     service: QueryQdrantService = Depends(QueryQdrantService),
# ):
#     """
#     Endpoint to fetch all news documents with pagination.
#     """
#     try:
#         data = await service.retrieve_news(
#             limit=limit, offset=offset, sort_by_recency=False
#         )
#         return {
#             "status": "success",
#             "count": len(data["results"]),
#             "next_offset": data["next_offset"],
#             "data": data["results"],
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@router.get(APIPath.NEWS)
async def get_latest_news(
    limit: int = Query(50, ge=1, le=1000),
    offset: str = Query(None, description="The offset ID for pagination"),
    service: QueryQdrantService = Depends(QueryQdrantService),
):
    """
    Endpoint to fetch the most recent news documents with pagination.
    """
    try:
        data = await service.retrieve_news(
            limit=limit, offset=offset, sort_by_recency=True
        )
        return {
            "status": "success",
            "count": len(data["results"]),
            "next_offset": data["next_offset"],
            "data": data["results"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get(APIPath.QUERY_TICKER_EVENTS)
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
