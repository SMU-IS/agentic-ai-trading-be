from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TickerInsight(BaseModel):
    ticker: str
    event_type: Optional[str] = None
    sentiment_score: float = Field(..., ge=-1, le=1)
    sentiment_label: str


class NewsMetadata(BaseModel):
    topic_id: str
    tickers: list[str]
    tickers_metadata: list[TickerInsight] = Field(default_factory=list)
    timestamp: datetime
    source_domain: str
    credibility_score: float = Field(..., ge=-1, le=1)
    headline: str
    text_content: str
    url: str
    author: str


class NewsAnalysisPayload(BaseModel):
    id: str
    metadata: NewsMetadata
