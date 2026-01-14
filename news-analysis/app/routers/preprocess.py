from typing import Union, List, Dict
from fastapi import APIRouter
from app.core.constant import APIPath
from app.services.preprocesser import PreprocessingService

router = APIRouter(tags=["Text Preprocessing"])

preprocessor = PreprocessingService()

@router.post(APIPath.PREPROCESS)
async def preprocess_endpoint(data: Union[Dict, List[Dict]]):
    return preprocessor.process_input(data)

