from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class QueryDocsRequest(BaseModel):
    query: str = Field(..., description="The search query")
    limit: int = Field(3, description="Number of results to return")
    tickers: list[str] = Field(..., description="List of tickers to filter by")
    start_date: Optional[datetime] = Field(None, description="The start date for filtering (ISO format)")
    end_date: Optional[datetime] = Field(None, description="The end date for filtering (ISO format)")
