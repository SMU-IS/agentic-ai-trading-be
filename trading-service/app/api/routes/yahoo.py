from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.yahoo_client import get_yahoo_client, YahooClient

router = APIRouter()


class QuotesResponse(BaseModel):
    data: Dict[str, List[Dict[str, Any]]]


class HistoryResponse(BaseModel):
    symbol: str
    interval: str
    count: int
    bars: List[Dict[str, Any]]


def get_client() -> YahooClient:
    return get_yahoo_client()


@router.get("/quotes", response_model=QuotesResponse)
async def get_quotes(
    symbols: Optional[List[str]] = Query(None, alias="symbol"),
    client: YahooClient = Depends(get_client),
) -> QuotesResponse:
    """
    Get intraday bars (1m, last 1d) for one or more tickers: /yahoo/quotes?symbol=AAPL&symbol=MSFT
    """
    try:
        data = client.get_quotes(symbols)
        return QuotesResponse(data=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{symbol}", response_model=HistoryResponse)
async def get_history(
    symbol: str,
    interval: str = Query("1d"),
    period: Optional[str] = Query(
        None,
        description="Yahoo period string, e.g. '5d','1mo','6mo','1y','max'",
    ),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    client: YahooClient = Depends(get_client),
) -> HistoryResponse:
    """
    Historical bars for a single ticker. Use either period OR start/end.
    """
    if not period and not start:
        raise HTTPException(
            status_code=400,
            detail="Provide either period or start (with optional end).",
        )
    try:
        result = client.get_history(
            symbol=symbol,
            start=start,
            end=end,
            interval=interval,
            period=period,
        )
        return HistoryResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
