from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import yfinance as yf  # type: ignore
from datetime import datetime
import time

@dataclass
class YahooClient:
    """Thin wrapper around yfinance."""

    def get_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        tickers = " ".join(symbols)
        data = yf.download(
            tickers=tickers,
            period="1d",
            interval="1m",
            auto_adjust=False,
            progress=False,
        )
        # yfinance returns multi-index for multiple tickers; normalize to dict
        result: Dict[str, Any] = {}
        if not symbols:
            return result
        
        for sym in symbols:
            try:
                df = data.xs(sym, axis=1, level=1)
            except Exception:
                result[sym] = []
                continue
            if df is None or df.empty:
                result[sym] = []
            else:
                result[sym] = [
                    {
                        "timestamp": idx.to_pydatetime().isoformat(),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"]),
                    }
                    for idx, row in df.iterrows()
                ]
        return result

    def get_history(
        self,
        symbol: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        interval: str = "1d",
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        If period is provided (e.g. '1d','5d','1mo','1y','max'), Yahoo ignores start/end.[web:3][web:14]
        """
        ticker = yf.Ticker(symbol)
        if period:
            hist = ticker.history(period=period, interval=interval)
        else:
            hist = ticker.history(start=start, end=end, interval=interval)

        bars = []
        if hist is not None and not hist.empty:
            for idx, row in hist.iterrows():
                bars.append(
                    {
                        "timestamp": idx.to_pydatetime().isoformat(),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"]),
                    }
                )

        return {
            "symbol": symbol,
            "interval": interval,
            "bars": bars,
            "count": len(bars),
        }
        
    def get_latest_info(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        """
        Fetch latest price, quote, and key metrics from Yahoo Finance.
        
        Returns:
            - lastPrice (fast_info - most recent)
            - currentPrice (info dict)
            - previousClose
            - open, dayHigh, dayLow
            - volume, marketCap, peRatio
            - 50DayAverage, 200DayAverage
        """
        ticker = yf.Ticker(symbol)
        
        # Fast info (lightweight, latest)
        fast = ticker.fast_info or {}
        
        # Full info (comprehensive)
        info = ticker.info or {}
        
        # Latest history bar (fallback)
        hist = ticker.history(period="1d")
        latest_bar = hist.iloc[-1].to_dict() if not hist.empty else {}
        
        return {
            "symbol": symbol,
            "timestamp": time.time(),
            "price": {
                "last_price": round(float(fast.get('lastPrice', 0)), 2),
                "current_price": round(float(info.get('currentPrice', 0)), 2),
                "previous_close": round(float(fast.get('previousClose', 0)), 2),
            },
            "intraday": {
                "open": round(float(latest_bar.get('Open', 0)), 2),
                "high": round(float(latest_bar.get('High', 0)), 2),
                "low": round(float(latest_bar.get('Low', 0)), 2),
                "volume": int(latest_bar.get('Volume', 0)),
            },
            "averages": {
                "sma_50": round(float(info.get('fiftyDayAverage', 0)), 2),
                "sma_200": round(float(info.get('twoHundredDayAverage', 0)), 2),
            },
            "fundamentals": {
                "market_cap": float(info.get('marketCap', 0)),
                "pe_ratio": round(float(info.get('trailingPE', 0)), 2),
                "forward_pe": round(float(info.get('forwardPE', 0)), 2),
            },
            "change": {
                "day_change_pct": round(
                    (fast.get('lastPrice', 0) - fast.get('previousClose', 0)) 
                    / fast.get('previousClose', 0) * 100, 2
                ),
            }
        }


_yahoo_client: Optional[YahooClient] = None


def get_yahoo_client() -> YahooClient:
    global _yahoo_client
    if _yahoo_client is None:
        _yahoo_client = YahooClient()
    return _yahoo_client
