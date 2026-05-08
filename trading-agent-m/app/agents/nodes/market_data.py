import asyncio
import httpx
from app.agents.state import AgentState, SignalData, MarketData, YahooTechnicalData
from app.core.config import env_config

TRADING_SERVICE_URL = env_config.trading_service_url

YAHOO_BASE_URL = f"{TRADING_SERVICE_URL}/yahoo"


class AssetNotTradableError(Exception):
    """Raised when a ticker is not available or not tradable on Alpaca."""


async def check_alpaca_asset(ticker: str) -> None:
    """
    Verify the ticker exists and is tradable on Alpaca.
    Raises AssetNotTradableError if not found or not tradable.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(
                f"{TRADING_SERVICE_URL}/assets/{ticker}",
                headers={"X-User-Id": "agent-A"},
            )
        except Exception as e:
            raise AssetNotTradableError(f"Asset check failed for {ticker}: {e}") from e

    if resp.status_code == 404:
        raise AssetNotTradableError(f"{ticker} not found on Alpaca")
    if resp.status_code != 200:
        raise AssetNotTradableError(f"Asset check error for {ticker} (status {resp.status_code})")

    data = resp.json()
    if not data.get("tradable"):
        status = data.get("status", "unknown")
        raise AssetNotTradableError(f"{ticker} is not tradable on Alpaca (status={status})")

    print(f"   [✅ Alpaca Asset] {ticker} — tradable={data['tradable']} | class={data.get('asset_class')} | exchange={data.get('exchange')}")


async def node_fetch_market_data(state: AgentState) -> AgentState:
    """
    Fetches real-time market data for the ticker from Yahoo Finance.
    Verifies the ticker is tradable on Alpaca first — raises AssetNotTradableError if not.
    """
    signal_data: SignalData = state["signal_data"]
    ticker = signal_data.ticker

    print(f"   [📊 Market Data] Fetching data for {ticker}...")

    await check_alpaca_asset(ticker)

    yahoo_data = await fetch_yahoo_technical(ticker)
    market_data = MarketData(
        yahoo=yahoo_data,
        timestamp=asyncio.get_event_loop().time(),
    )
    state["market_data"] = market_data
    print(market_data.to_prompt())
    print("   [✅ Market Data Fetched] Yahoo data added to state.")

    return state


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
                raise RuntimeError(f"Yahoo unavailable (status {resp.status_code})")

            data = resp.json()
            tech = YahooTechnicalData.from_dict(data)
            return tech
        except Exception as e:
            print(f"   [❌ Yahoo API] {e}")
            raise

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