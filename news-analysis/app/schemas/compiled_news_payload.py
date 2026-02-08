from datetime import datetime
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field


class TickerSentimentData(BaseModel):
    """Sentiment data for a single ticker"""
    sentiment_score: float = Field(..., ge=-1, le=1)
    sentiment_label: str
    confidence: float = Field(..., ge=0, le=1)
    reasoning: str
    official_name: str


class TickerMetadataItem(BaseModel):
    """Metadata for a single ticker including sentiment"""
    OfficialName: str
    NameIdentified: Optional[List[str]] = None
    event_type: Optional[str] = None
    event_proposal: Optional[str] = None
    sentiment_score: Optional[float] = Field(None, ge=-1, le=1)
    sentiment_label: Optional[str] = None
    sentiment_confidence: Optional[float] = Field(None, ge=0, le=1)
    sentiment_reasoning: Optional[str] = None


class SentimentAnalysis(BaseModel):
    """Overall sentiment analysis results"""
    overall_sentiment_score: float = Field(..., ge=-1, le=1)
    overall_sentiment_label: str
    analysis_successful: bool = True
    ticker_sentiments: Dict[str, TickerSentimentData] = {}
    error: Optional[str] = None


class NewsMetadata(BaseModel):
    article_id: str
    tickers: List[str]
    timestamp: datetime
    source_domain: str
    event_type: str
    # Overall sentiment (weighted average of per-ticker sentiments)
    sentiment_score: float = Field(..., ge=-1, le=1)
    sentiment_label: str
    sentiment_confidence: Optional[float] = Field(None, ge=0, le=1)
    headline: str
    text_content: str
    url: str
    author: Optional[str] = None
    # Per-ticker metadata with sentiment
    ticker_metadata: Optional[Dict[str, Any]] = None
    # Full sentiment analysis results
    sentiment_analysis: Optional[Dict[str, Any]] = None


class NewsAnalysisPayload(BaseModel):
    id: str
    metadata: NewsMetadata
