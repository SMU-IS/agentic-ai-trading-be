from typing import Dict, List, Union

from app.core.constant import APIPath
from app.services._01_preprocesser import PreprocessingService
from fastapi import APIRouter

router = APIRouter(tags=["Text Preprocessing"])

preprocessor = PreprocessingService()


@router.post(APIPath.PREPROCESS)
async def preprocess_endpoint(data: Union[Dict, List[Dict]]):
    return preprocessor.process_input(data)
