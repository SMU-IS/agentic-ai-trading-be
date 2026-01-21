from typing import Optional

from pydantic import BaseModel, Field


class NewsPayload(BaseModel):
    """
    Schema for incoming news data from Scraper Service.
    """

    id: str
    headline: str
    content: str
    source: Optional[str] = None


class LLMEventResult(BaseModel):
    """
    Schema for the raw output expected from the LLM.
    """

    is_event: bool = Field(
        description="True if a significant investment event is present"
    )
    event_category: str = Field(
        description="Category of the event (e.g., earnings, merger, macro, none)"
    )
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(
        description="Brief explanation of why this is or isn't an event"
    )


class EventResponse(BaseModel):
    """
    Schema for the final API response returned to the client.
    """

    event_detected: bool
    event_type: Optional[str] = None
    confidence: float
    method: str
    summary: Optional[str] = None
