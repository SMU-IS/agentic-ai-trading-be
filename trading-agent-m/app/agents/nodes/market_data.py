import httpx
import asyncio
from typing import Dict, Any, List
from app.agents.state import AgentState
import os
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "http://localhost:9000/api/brokerage")
YAHOO_BASE_URL = os.getenv("YAHOO_BASE_URL", "http://localhost:9000/api/yahoo")


async def node_fetch_market_data(state: AgentState) -> AgentState:
    """
    Fetches real-time market data for the ticker:
    - Latest quote/trade from Alpaca brokerage API
    - Recent historical bars from Yahoo API
    """
    ticker = state["ticker"]
    print(f"   [📊 Market Data] Fetching data for {ticker}...")

    # Parallel API calls
    alpaca_task = fetch_alpaca_data(ticker)
    yahoo_task = fetch_yahoo_historical(ticker)
    
    alpaca_data, yahoo_data = await asyncio.gather(alpaca_task, yahoo_task)
    
    state["market_data"] = {
        "alpaca": alpaca_data,
        "yahoo": yahoo_data,
        "timestamp": asyncio.get_event_loop().time()
    }
    
    print(f"   [✅ Market Data] {ticker}: bid=${alpaca_data.get('bid_price', 'N/A')}, "
          f"latest={alpaca_data.get('price', 'N/A')}, "
          f"{len(yahoo_data.get('bars', []))} Yahoo bars")
    
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
            
            return {
                "latest_quote": quote_data,
                "latest_trade": trade_data,
                "spread": (
                    quote_data.get("ask_price") - quote_data.get("bid_price")
                    if quote_data.get("ask_price") and quote_data.get("bid_price") else None
                )
            }
        except Exception as e:
            print(f"   [❌ Alpaca API] {e}")
            return {"error": str(e)}

# async def fetch_yahoo_historical(ticker: str) -> Dict[str, Any]:
#     """Yahoo recent historical (last 5 days daily)."""
#     async with httpx.AsyncClient(timeout=10.0) as client:
#         try:
#             resp = await client.get(
#                 f"{YAHOO_BASE_URL}/quotes",
#                 params={"symbol": ticker, "interval": "1d", "period": "1w"}
#             )
#             return resp.json() if resp.status_code == 200 else {"error": "Yahoo unavailable"}
#         except Exception as e:
#             print(f"   [❌ Yahoo API] {e}")
#             return {"error": str(e)}


async def fetch_yahoo_historical(ticker: str) -> Dict[str, Any]:
    """Fetch Yahoo historical + key indicators for LLM prompts."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{YAHOO_BASE_URL}/history/{ticker}",
                params={"interval": "1d", "period": "1mo"}
            )
            if resp.status_code != 200:
                return {"error": "Yahoo unavailable"}
            
            data = resp.json()
            bars = data.get('bars', [])
            if not bars:
                return {"error": "No bars data"}
            
            df = pd.DataFrame(bars)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            df = df[['open','high','low','close','volume']].astype(float)
            
            # Compact indicators
            tr = pd.concat([
                df['high']-df['low'], 
                abs(df['high']-df['close'].shift()), 
                abs(df['low']-df['close'].shift())
            ], axis=1).max(axis=1)
            
            return {
                "raw_data": bars,
                "indicators": {
                    "price": float(df['close'].iloc[-1]),
                    "atr14": float(tr.rolling(14).mean().iloc[-1]),
                    "sma20": float(df['close'].rolling(20).mean().iloc[-1]),
                    "sma50": float(df['close'].rolling(50).mean().iloc[-1]),
                    "support": float(df['low'].tail(20).min()),
                    "resistance": float(df['high'].tail(20).max())
                },
                "summary": f"{df.shape[0]} bars, {df.index[0].date()}→{df.index[-1].date()}"
            }
        except Exception as e:
            return {"error": str(e)}
