from app.core.constant import APIPath
from app.core.security import get_current_user
from app.schemas.ingestion import Ingestion
from app.services.ingestion_service import IngestionService
from fastapi import APIRouter, BackgroundTasks, Depends

"""
# TODO: To be removed
Not needed. News Analysis Module will ingest the necessary documents into Qdrant.
Only for testing purposes.
"""


router = APIRouter(tags=["Ingest Documents"], dependencies=[Depends(get_current_user)])


_ingestion_instance = IngestionService()


def get_ingestion_service():
    return _ingestion_instance


@router.post(APIPath.INGEST_DOCUMENTS)
async def ingest_documents(
    request: Ingestion,
    background_tasks: BackgroundTasks,
    service: IngestionService = Depends(get_ingestion_service),
):
    """
    Ingest documents from provided URLs.
    """

    url_strings = [str(url) for url in request.urls]
    background_tasks.add_task(service.ingest_docs, url_strings)

    return {"message": "Ingestion process started for provided URLs."}
