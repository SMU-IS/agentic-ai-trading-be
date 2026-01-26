from pydantic import BaseModel, Field


class QueryDocsRequest(BaseModel):
    q: str = Field(..., description="The search query")
    limit: int = Field(3, description="Number of results to return")
    threshold: float = Field(0.0, description="Minimum similarity score")
