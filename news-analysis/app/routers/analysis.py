from typing import Dict, List, Union
from fastapi import APIRouter

from app.core.constant import APIPath
from app.services.sentiment import SentimentAnalyzer

router = APIRouter(tags=["Text Analysis"])

# Initialize sentiment analyzer
sentiment_analyzer = SentimentAnalyzer()


@router.post(APIPath.ANALYSE)
async def analysis_endpoint(data: Union[Dict, List[Dict]]):
    # Handle single dict or list of dicts
    if isinstance(data, dict):
        data = [data]
    
    analysed_data = []
    for item in data: 
        result = sentiment_analyzer.process(item)
        analysed_data.append(result)
    
    return analysed_data