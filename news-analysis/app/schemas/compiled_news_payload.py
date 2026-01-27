from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NewsMetadata(BaseModel):
    article_id: str
    tickers: List[str]
    timestamp: datetime
    source_domain: str
    event_type: str
    credibility_score: float = Field(..., ge=0, le=1)
    sentiment_score: float = Field(..., ge=-1, le=1)
    sentiment_label: str
    headline: str
    text_content: str
    url: str
    author: Optional[str] = None


class NewsAnalysisPayload(BaseModel):
    id: str
    metadata: NewsMetadata
