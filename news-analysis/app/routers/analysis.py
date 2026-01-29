"""
Sentiment Analysis Router
File: news-analysis/app/routers/analysis.py (UPDATE THIS FILE)

Add these routes to your existing analysis.py router
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import List, Optional
import logging

# Import your sentiment service
from app.services._05_sentiment import sentiment_service

logger = logging.getLogger(__name__)

# If you have a separate router for sentiment, create this:
# Otherwise, add these endpoints to your existing analysis.py router

router = APIRouter(
    prefix="/sentiment",
    tags=["Sentiment Analysis"]
)


# Request/Response Models
class SentimentRequest(BaseModel):
    """Request model for single text analysis"""
    text: str = Field(..., min_length=1, max_length=10000)
    emoji_weight: Optional[float] = Field(0.3, ge=0.0, le=1.0)
    text_weight: Optional[float] = Field(0.7, ge=0.0, le=1.0)
    
    @validator('text')
    def text_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Text cannot be empty')
        return v


class BatchSentimentRequest(BaseModel):
    """Request model for batch analysis (matching your JSON structure)"""
    items: List[dict] = Field(..., min_items=1, max_items=1000)
    emoji_weight: Optional[float] = Field(0.3, ge=0.0, le=1.0)
    text_weight: Optional[float] = Field(0.7, ge=0.0, le=1.0)


class SentimentResponse(BaseModel):
    """Response model matching your JSON schema"""
    sentiment_score: float
    sentiment_label: str
    confidence: float
    models_used: List[str]
    
    class Config:
        schema_extra = {
            "example": {
                "sentiment_score": 0.24192,
                "sentiment_label": "positive",
                "confidence": 0.62107,
                "models_used": ["FinBERT", "VADER"]
            }
        }


class BatchSentimentResponse(BaseModel):
    """Response for batch processing"""
    items: List[dict]
    total_processed: int
    success_count: int
    error_count: int


# Routes
@router.post("/analyze", response_model=SentimentResponse)
async def analyze_sentiment(request: SentimentRequest):
    """
    Analyze sentiment of a single text
    
    - **text**: Text to analyze
    - **emoji_weight**: Weight for emoji sentiment (default: 0.3)
    - **text_weight**: Weight for text sentiment (default: 0.7)
    """
    try:
        result = sentiment_service.analyze_text(
            text=request.text,
            emoji_weight=request.emoji_weight,
            text_weight=request.text_weight
        )
        
        return SentimentResponse(
            sentiment_score=round(result.sentiment_score, 6),
            sentiment_label=result.sentiment_label,
            confidence=round(result.confidence, 6),
            models_used=result.models_used
        )
    
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sentiment analysis failed: {str(e)}"
        )


@router.post("/analyze/batch", response_model=BatchSentimentResponse)
async def batch_analyze_sentiment(request: BatchSentimentRequest):
    """
    Analyze sentiment for multiple items in batch
    
    Expects items in the format from cleaned_dummy.json
    """
    try:
        # Process batch
        results = sentiment_service.process_batch(request.items)
        
        # Count successes and errors
        success_count = sum(1 for item in results if 'sentiment_label' in item)
        error_count = len(results) - success_count
        
        return BatchSentimentResponse(
            items=results,
            total_processed=len(results),
            success_count=success_count,
            error_count=error_count
        )
    
    except Exception as e:
        logger.error(f"Batch sentiment analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch analysis failed: {str(e)}"
        )


@router.get("/health")
async def sentiment_health_check():
    """Health check for sentiment service"""
    try:
        # Quick test
        test_result = sentiment_service.analyze_text("Test message")
        return {
            "status": "healthy",
            "service": "sentiment_analysis",
            "model_loaded": True,
            "device": sentiment_service.device
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "sentiment_analysis",
            "error": str(e),
            "model_loaded": False
        }


@router.get("/models/info")
async def get_sentiment_models_info():
    """Get information about loaded models"""
    return {
        "primary_model": "ProsusAI/finbert",
        "emoji_analyzer": "Custom Emoji Mapping + VADER",
        "device": sentiment_service.device,
        "supported_features": [
            "Financial text analysis",
            "Emoji sentiment detection",
            "Reddit slang recognition",
            "Batch processing"
        ],
        "emoji_weight_default": 0.3,
        "text_weight_default": 0.7
    }