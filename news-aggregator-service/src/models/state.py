from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

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
    confidence: int = Field(..., description="1-10 scale")
    trade_rationale: str = Field(..., description="Why this signal")
    position_size_pct: float = Field(..., description="0.5|1|2")
    stop_loss_pct: float = Field(..., description="8|10|12")
    target_pct: float = Field(..., description="20|30|50")

    def to_dict(self) -> Dict[str, Any]:
        """Convert DeepAnalysis to dictionary, recursively handling nested models."""
        result = {}
        for field_name, field_info in self.model_fields.items():
            value = getattr(self, field_name)
            if hasattr(value, 'to_dict'):  # Custom model with to_dict method
                result[field_name] = value.to_dict()
            elif hasattr(value, 'model_dump'):  # Pydantic BaseModel
                result[field_name] = value.model_dump()
            elif isinstance(value, (list, dict)):
                result[field_name] = value  # Lists and dicts pass through
            else:
                result[field_name] = value
        return result

class Signal(BaseModel):
    ticker: str = Field(..., description="Stock ticker")
    position_size_pct: float = Field(..., description="0.5|1|2")
    stop_loss_pct: float = Field(..., description="8|10|12")
    target_pct: float = Field(..., description="20|30|50")
    trade_rationale: str = Field(..., description="Why this signal")

class SentimentLabel(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

@dataclass
class TickerSentiment:
    ticker: str = ""
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
        # ensure enum is serialized as string
        if isinstance(self.sentiment_label, SentimentLabel):
            data['sentiment_label'] = self.sentiment_label.value
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
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            try:
                data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            except Exception:
                data['timestamp'] = datetime.now()

        # Convert label string back to enum if needed
        if isinstance(data.get('sentiment_label'), str):
            try:
                data['sentiment_label'] = SentimentLabel(data['sentiment_label'])
            except ValueError:
                data['sentiment_label'] = SentimentLabel.NEUTRAL

        return cls(**data)

    @classmethod
    def from_stream_event(cls, data: dict):
        """
        Adapter for stream-style payloads like:

        {
            "event_type": "NEWS_UPDATE",
            "id": "reddit:1r0tftt",
            "ticker": "IBRX",
            "event_type_meta": "REGULATORY_APPROVAL",
            "sentiment_score": 0.85,
            "sentiment_confidence": 0.6145,
            "event_description": "Saudi SFDA approval for ANKTIVA in NMIBC CIS",
            "sentiment_reasoning": "..."
        }
        """
        init: dict = {}

        # direct mappings
        init['ticker'] = data.get('ticker', '')
        init['event_type'] = data.get('event_type_meta', '')
        init['event_description'] = data.get('event_description', '')
        init['sentiment_score'] = float(data.get('sentiment_score', 0.0))
        init['sentiment_confidence'] = float(data.get('sentiment_confidence', 0.0))
        init['sentiment_reasoning'] = data.get('sentiment_reasoning', '')

        # optional: use stream id as OfficialName or just ignore
        # init['OfficialName'] = data.get('id', '')

        # derive sentiment_label from score if not provided
        score = init['sentiment_score']
        if score > 0.15:
            init['sentiment_label'] = SentimentLabel.BULLISH
        elif score < -0.15:
            init['sentiment_label'] = SentimentLabel.BEARISH
        else:
            init['sentiment_label'] = SentimentLabel.NEUTRAL

        # let __post_init__ populate NameIdentified, timestamp, etc.
        return cls(**init)