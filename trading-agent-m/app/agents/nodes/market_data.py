import asyncio
from typing import Any, Dict
import httpx
import pandas as pd
from app.agents.state import AgentState, YahooData, SignalData, AlpacaData, Quote, Trade, MarketData
from app.core.config import env_config

TRADING_SERVICE_URL = env_config.trading_service_url

ALPACA_BASE_URL = TRADING_SERVICE_URL
YAHOO_BASE_URL = f"{TRADING_SERVICE_URL}/yahoo"


async def node_fetch_market_data(state: AgentState) -> AgentState:
    """
    Fetches real-time market data for the ticker:
    - Latest quote/trade from Alpaca brokerage API
    - Recent historical bars from Yahoo API
    """
    signal_data: SignalData = state["signal_data"]
    ticker = signal_data.ticker

    print(f"   [📊 Market Data] Fetching data for {ticker}...")

    # Parallel API calls
    alpaca_task = fetch_alpaca_data(ticker)
    yahoo_task = fetch_yahoo_historical(ticker)

    alpaca_data, yahoo_data = await asyncio.gather(alpaca_task, yahoo_task)
    market_data = MarketData(
        alpaca=alpaca_data,
        yahoo=yahoo_data,
        timestamp=asyncio.get_event_loop().time(),
    )
    state["market_data"] = market_data
    print(market_data.to_prompt())
    print("   [✅ Market Data Fetched] Alpaca and Yahoo data added to state.")
    
    return state


async def fetch_alpaca_data(ticker: str) -> Dict[str, Any]:
    """Alpaca latest quote + trade."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Latest quote
            quote_resp = await client.get(f"{ALPACA_BASE_URL}/latest_quote/{ticker}")
            quote_data = quote_resp.json() if quote_resp.status_code == 200 else {}

            # Latest trade
            trade_resp = await client.get(f"{ALPACA_BASE_URL}/latest_trade/{ticker}")
            trade_data = trade_resp.json() if trade_resp.status_code == 200 else {}
            return AlpacaData(
                latest_quote=Quote(**quote_data) if quote_data else None,
                latest_trade=Trade(**trade_data) if trade_data else None,
                spread=(
                    quote_data.get("ask_price") - quote_data.get("bid_price")
                    if quote_data.get("ask_price") and quote_data.get("bid_price")
                    else 0.0
                ),
            )
        except Exception as e:
            print(f"   [❌ Alpaca API] {e}")
            return {"error": str(e)}


async def fetch_yahoo_historical(ticker: str) -> YahooData:
    """Fetch Yahoo historical + key indicators for LLM prompts."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{YAHOO_BASE_URL}/history/{ticker}",
                params={"interval": "1d", "period": "3mo"},
            )
            if resp.status_code != 200:
                return {"error": "Yahoo unavailable"}

            data = resp.json()
            bars = data.get("bars", [])
            if not bars:
                return {"error": "No bars data"}

            df = pd.DataFrame(bars)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
            df = df[["open", "high", "low", "close", "volume"]].astype(float)

            # Compact indicators
            tr = pd.concat(
                [
                    df["high"] - df["low"],
                    abs(df["high"] - df["close"].shift()),
                    abs(df["low"] - df["close"].shift()),
                ],
                axis=1,
            ).max(axis=1)
            return YahooData(
                price=float(df["close"].iloc[-1]),
                atr14=float(tr.rolling(14).mean().iloc[-1]),
                sma20=float(df["close"].rolling(20).mean().iloc[-1]),
                sma50=float(df["close"].rolling(50).mean().iloc[-1]),
                support=float(df["low"].tail(30).min()),
                resistance=float(df["high"].tail(30).max()),
                rsi14=float(rsi(df["close"], 14).iloc[-1]),
                summary=f"{df.shape[0]} bars, {df.index[0].date()}→{df.index[-1].date()}",
            )
        except Exception as e:
            return {"error": str(e)}


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val
