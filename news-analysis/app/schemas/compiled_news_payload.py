from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class TickerEvent(BaseModel):
    event_type: str


class NewsMetadata(BaseModel):
    article_id: str
    tickers_metadata: Dict[str, TickerEvent]
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
