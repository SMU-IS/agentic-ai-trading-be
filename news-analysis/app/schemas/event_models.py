from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NewsPayload(BaseModel):
    headline: str = Field(..., alias="clean_title")
    content: str = Field(..., alias="clean_combined")
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class EventResponse(BaseModel):
    is_event: bool
    event_type: str | None = None
    ticker: Optional[str] = None
    method: str
    summary: str


class LLMEventResult(BaseModel):
    is_event: bool
    event_category: str
    reasoning: str
