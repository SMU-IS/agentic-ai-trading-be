import asyncio
from typing import Any, Dict
import httpx
from app.agents.state import AgentState, SignalData, AlpacaData, Quote, Trade, MarketData, YahooTechnicalData
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
    yahoo_task = fetch_yahoo_technical(ticker)

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


async def fetch_yahoo_technical(ticker: str) -> YahooTechnicalData:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{YAHOO_BASE_URL}/analyze",
                params={
                    "symbol": ticker
                }
            )
            if resp.status_code != 200:
                return {"error": "Yahoo unavailable"}

            data = resp.json()
            tech = YahooTechnicalData.from_dict(data)
            return tech
        except Exception as e:
            return {"error": str(e)}

async def test():
    """Async comprehensive test for YahooTechnicalData pipeline."""
    print("🧪 Testing Yahoo Technical Data Pipeline (Async)...")
    
    tech_data: YahooTechnicalData = await fetch_yahoo_technical("NVDA")
    print(tech_data)
    x = tech_data.to_prompt()
    print(x)

if __name__ == "__main__":
    # Run async test
    import asyncio
    asyncio.run(test())