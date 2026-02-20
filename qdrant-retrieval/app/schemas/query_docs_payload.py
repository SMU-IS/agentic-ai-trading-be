from pydantic import BaseModel, Field


class QueryDocsRequest(BaseModel):
    query: str = Field(..., description="The search query")
    limit: int = Field(3, description="Number of results to return")
    tickers: list[str] = Field(..., description="List of tickers to filter by")
