from app.core.config import env_config
from app.core.constant import APIPath
from app.core.security import get_current_user
from app.providers.vector.registry import get_vector_strategy
from app.schemas.ingestion import Ingestion
from app.services.ingestion_service import IngestionService
from fastapi import APIRouter, BackgroundTasks, Depends

"""
# TODO: To be removed
Not needed. News Analysis Module will ingest the necessary documents into Qdrant.
Only for testing purposes.
"""


router = APIRouter(tags=["Ingest Documents"], dependencies=[Depends(get_current_user)])


def get_ingestion_service() -> IngestionService:
    """
    Factory function to provide a fully configured IngestionService.
    It resolves the storage strategy dynamically.
    """

    vector_strat = get_vector_strategy(env_config.storage_provider)
    vector_store_instance = vector_strat.get_vector_store()
    ingestion_sevice = IngestionService(vector_store_instance)

    return ingestion_sevice


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
