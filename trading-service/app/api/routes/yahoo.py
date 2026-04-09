from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.yahoo_client import get_yahoo_client, YahooClient
from app.api.schemas import SignalResponse, QuotesResponse, HistoryResponse, LatestInfoResponse
from app.api.routes.brokerage import get_broker
from app.core.broker_client import AlpacaBrokerClient

router = APIRouter()


def get_client() -> YahooClient:
    return get_yahoo_client()

@router.get("/analyze")
async def analyze_signals(
    symbol: str = Query(..., alias="symbol", description="Single ticker symbol (e.g. NVDA)"),
    client: YahooClient = Depends(get_client),
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> SignalResponse:
    try:
        data: SignalResponse = client.process_trading_data(symbol)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

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


@router.get("/latest/{symbol}", response_model=LatestInfoResponse)
async def get_latest_info(
    symbol: str,
    client: YahooClient = Depends(get_client),
) -> LatestInfoResponse:
    """
    Latest price, quote, and key metrics for a ticker.
    
    **Perfect for**:
    - LLM trade prompts (current price)
    - Risk sizing (entry_price validation)
    - Real-time dashboards
    
    **Example**:
    ```
    GET /latest/AAPL → {"price": {"last_price": 258.27, "day_change_pct": -1.25}, ...}
    ```
    """
    try:
        result = client.get_latest_info(symbol)
        return LatestInfoResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Latest info failed: {str(e)}")