from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Content(BaseModel):
    title: str
    body: str
    clean_title: str
    clean_body: str
    clean_combined_withurl: str
    clean_combined_withouturl: str


class Engagement(BaseModel):
    total_comments: int = Field(..., ge=0)
    score: int
    upvote_ratio: float = Field(..., ge=0, le=1)


class SubredditMetadata(BaseModel):
    subreddit: str
    category: Optional[str] = None


class TickerDetail(BaseModel):
    type: str
    official_name: str
    name_identified: list[str]
    event_type: Optional[str] = None
    event_description: Optional[str] = None
    event_proposal: Optional[EventProposal] = None
    sentiment_score: float = Field(..., ge=-1, le=1)
    sentiment_label: str
    sentiment_confidence: float = Field(..., ge=0, le=1)
    sentiment_reasoning: str

class EventProposal(BaseModel):
    proposed_event_name: str


class RedditFields(BaseModel):
    id: str
    content_type: str
    native_id: str
    source: str
    author: str
    url: str
    timestamps: datetime
    content: Content
    engagement: Engagement
    metadata: SubredditMetadata
    images: list[Any] = []
    links: list[Any] = []
    ticker_metadata: dict[str, TickerDetail]


class RedditSourcePayload(BaseModel):
    id: str
    fields: RedditFields
