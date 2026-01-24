from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import yfinance as yf  # type: ignore
from datetime import datetime

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

        if len(symbols) == 1:
            sym = symbols[0]
            if data is None or data.empty:
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
                    for idx, row in data.iterrows()
                ]
            return result

        # multi-ticker case
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


_yahoo_client: Optional[YahooClient] = None


def get_yahoo_client() -> YahooClient:
    global _yahoo_client
    if _yahoo_client is None:
        _yahoo_client = YahooClient()
    return _yahoo_client
