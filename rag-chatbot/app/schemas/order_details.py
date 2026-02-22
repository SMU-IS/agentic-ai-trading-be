from pydantic import BaseModel


# TODO: Update Schema
class OrderDetailsResponse(BaseModel):
    ticker: str
    action: str
    entry_price: float
    reasoning: str
