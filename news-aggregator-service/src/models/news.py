from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
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

class Credibility(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium" 
    HIGH = "High"

class TradeSignal(str, Enum):
    BUY = "BUY"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"

class DeepAnalysis(BaseModel):
    ticker: str = Field(..., description="Stock ticker")
    rumor_summary: str = Field(..., description="1-sentence recap")
    credibility: Credibility = Field(..., description="Low|Medium|High")
    credibility_reason: str = Field(..., description="2-3 sentences")
    references: List[str] = Field(default_factory=list, description="URLs/sources")
    trade_signal: TradeSignal = Field(..., description="BUY|SHORT|NO_TRADE")
    confidence: int = Field(ge=1, le=10, description="1-10 scale")
    trade_rationale: str = Field(..., description="Why this signal")
    position_size_pct: float = Field(ge=0, le=5, description="0.5|1|2")
    stop_loss_pct: float = Field(ge=5, le=15, description="8|10|12")
    target_pct: float = Field(ge=10, le=60, description="20|30|50")

class TradingSignal(BaseModel):
    ticker: str
    signal_type: str  # "BUY", "SELL", "HOLD", "ALERT"
    confidence: float
    urgency: str  # "HIGH", "MEDIUM", "LOW"
    position_size: Optional[float] = None
    risk_limit: float
    reasoning: str
    timestamp: datetime


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative" 
    NEUTRAL = "neutral"

@dataclass
class TickerSentiment:
    ticker: str = ""  # ← EXPLICITLY SAVED TICKER SYMBOL
    Type: str = "stock"
    OfficialName: str = ""
    NameIdentified: List[str] = field(default_factory=list)
    event_type: str = ""
    event_description: str = ""
    event_proposal: Optional[str] = None
    sentiment_score: float = 0.0
    sentiment_label: SentimentLabel = SentimentLabel.NEUTRAL
    sentiment_confidence: float = 0.0
    sentiment_reasoning: str = ""
    
    # Optional metadata
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        # Ensure ticker is in NameIdentified if empty
        if self.ticker and not self.NameIdentified:
            self.NameIdentified = [self.ticker]
    
    def to_dict(self):
        """Convert to JSON-serializable dict"""
        data = {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
        if self.timestamp:
            data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict, ticker: str = None):
        """Create from dict/JSON - extracts ticker from key or explicit param"""
        # Use explicit ticker or first NameIdentified
        if ticker:
            data['ticker'] = ticker
        elif data.get('NameIdentified') and data['NameIdentified']:
            data['ticker'] = data['NameIdentified'][0]
        else:
            data['ticker'] = "UNKNOWN"
        
        # Handle null strings
        if data.get('event_proposal') in ('null', 'None', ''):
            data['event_proposal'] = None
        
        # Convert timestamp
        if 'timestamp' in data:
            try:
                data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            except:
                data['timestamp'] = datetime.now()
        
        return cls(**data)