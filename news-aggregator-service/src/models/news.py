from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class NewsArticle(BaseModel):
    id: str
    title: str
    content: str
    sentiment: float = Field(..., ge=-1.0, le=1.0)
    timestamp: datetime
    source: str

class TickerTopic(BaseModel):
    ticker: str
    topic: str
    sentiment: float
    volume: int = 0
    articles: List[str] = []

class ResearchQuestion(BaseModel):
    question: str
    sources_needed: List[str]

class DeepAnalysis(BaseModel):
    ticker: str
    topic: str
    verified: bool
    confidence: float
    summary: str
    research_questions: List[ResearchQuestion]

class TradingSignal(BaseModel):
    ticker: str
    signal_type: str  # "BUY", "SELL", "HOLD", "ALERT"
    confidence: float
    urgency: str  # "HIGH", "MEDIUM", "LOW"
    position_size: Optional[float] = None
    risk_limit: float
    reasoning: str
    timestamp: datetime
