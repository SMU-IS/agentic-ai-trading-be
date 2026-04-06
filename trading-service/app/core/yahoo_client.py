from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import yfinance as yf  # type: ignore
from datetime import datetime
import time
import pandas as pd
import numpy as np
from app.api.schemas import SignalResponse


@dataclass
class YahooClient:
    """Thin wrapper around yfinance."""

    def get_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        tickers = " ".join(symbols)
        data = yf.download(
            tickers=tickers,
            period="1mo",
            interval="1d",
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

    @staticmethod
    def _session_progress_from_clock(clock: dict) -> float:
        """
        Returns fraction of NYSE session elapsed (0.0–1.0) using clock data.
        Formula: elapsed = total_session - time_remaining
        Total session is always 390 minutes (9:30–16:00 ET).
        Returns 1.0 when market is closed so vol_ratio is never projected.
        """
        if not clock or not clock.get("is_open"):
            return 1.0
        try:
            now   = datetime.fromisoformat(clock["timestamp"])
            close = datetime.fromisoformat(clock["next_close"])
            total_sec = 390 * 60
            remaining = (close - now).total_seconds()
            elapsed   = total_sec - remaining
            return max(0.01, min(1.0, elapsed / total_sec))
        except Exception:
            return 1.0  # fallback: treat session as complete, use raw volume

    # Fundamentals
    def process_trading_data(self, ticker: str, clock: dict = None) -> SignalResponse:
        """Process 1y daily data for all trading signals."""
        data = yf.download(
            tickers=ticker,
            period="1y",  # Gets ~5-7 trading days
            interval="1d",
            auto_adjust=False,
            progress=False,
        )
        results: Dict[str, pd.DataFrame] = {}

        if data.empty:
            return results

        df = data.xs(ticker, axis=1, level=1).copy()
        signals_df = self.calculate_all_signals(df)
        latest_row = signals_df.iloc[-1]
        signals_dict = self._to_json_safe(latest_row)

        # ── Vol ratio projection ──────────────────────────────────
        # Today's volume is partial (intraday). Project to full-session
        # equivalent so the vol gate reflects true participation rate.
        pct_elapsed = self._session_progress_from_clock(clock)
        print(f"Session progress: {pct_elapsed*100:.1f}% (clock: {clock})")
        if 0 < pct_elapsed < 1.0:
            raw_volume = signals_dict.get("Volume", 0)
            vol_avg20  = signals_dict.get("vol_avg20", 0)
            if raw_volume > 0 and vol_avg20 and vol_avg20 > 0:
                projected = raw_volume / pct_elapsed        # full-session estimate
                signals_dict["vol_ratio"] = round(projected / vol_avg20, 2)

        ticker = yf.Ticker(ticker).info
        market_cap = float(ticker.get('marketCap', 0))
        signals_dict["is_penny"] = signals_dict["is_penny"] and (market_cap < 300_000_000)
        current_price = float(ticker.get('currentPrice', 0))

        # summary
        first_date = df.index[0].strftime('%b %d, %Y')
        last_date = df.index[-1].strftime('%b %d, %Y')
        trading_days = len(df)

        signals_dict['period_summary'] = f"{first_date} - {last_date} ({trading_days} trading days)"

        return SignalResponse(
            current_price=current_price,
            # Raw OHLCV
            open=signals_dict['Open'],
            high=signals_dict['High'],
            low=signals_dict['Low'],
            close=signals_dict['Close'],
            adj_close=signals_dict['Adj Close'],
            volume=int(signals_dict['Volume']),
            
            # All your signal fields
            candle_type=signals_dict['candle_type'],
            body_size=round(signals_dict['body_size'], 3),
            body_pct=round(signals_dict['body_pct'], 3),
            upper_wick=round(signals_dict['upper_wick'], 3),
            lower_wick=round(signals_dict['lower_wick'], 3),
            rsi=round(signals_dict['RSI'], 2),
            vol_ratio=round(signals_dict['vol_ratio'], 2),
            atr14=round(signals_dict['ATR'], 3),
            sma20=signals_dict['SMA20'],
            sma50=signals_dict['SMA50'],
            sma200=signals_dict['SMA200'],
            golden_cross=signals_dict['golden_cross'],
            death_cross=signals_dict['death_cross'],
            high_3d=round(signals_dict["high_3d"], 3),
            low_3d=round(signals_dict['low_3d'], 3),
            is_penny=signals_dict['is_penny'],
            support=round(signals_dict['support'], 3),
            resistance=round(signals_dict['resistance'], 3),
            period_summary=signals_dict['period_summary'],
            # MACD
            macd=round(signals_dict['macd'], 4),
            macd_signal=round(signals_dict['macd_signal'], 4),
            macd_histogram=round(signals_dict['macd_histogram'], 4),
            macd_bullish=signals_dict['macd_bullish'],
            macd_bearish=signals_dict['macd_bearish'],
            
            # Bollinger Bands
            bb_upper=round(signals_dict['bb_upper'], 3),
            bb_middle=round(signals_dict['bb_middle'], 3),
            bb_lower=round(signals_dict['bb_lower'], 3),
            bb_width=round(signals_dict['bb_width'], 3),
            bb_position=round(signals_dict['bb_position'], 3),
            bb_squeeze=signals_dict['bb_squeeze'],
            bb_upper_break=signals_dict['bb_upper_break'],
            bb_lower_break=signals_dict['bb_lower_break'],
        )

    def calculate_all_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators for profile triggers."""
        df = df.copy().dropna()

        # Basic OHLC metrics
        df["body_size"] = (df["Close"] - df["Open"]).abs() / df["Open"] * 100
        df["range"] = df["High"] - df["Low"]
        df["range_safe"] = df["range"].replace(0, np.nan)

        df["body_pct"] = ((df["Close"] - df["Open"]).abs() / df["range_safe"]).fillna(0)
        df["upper_wick"] = df["High"] - df[["Open", "Close"]].max(axis=1)
        df["lower_wick"] = df[["Open", "Close"]].min(axis=1) - df["Low"]

        # Candle classification
        df["candle_type"] = self.classify_candle(df)

        # Moving averages (on 1mo data these will be mostly NaN for 50/200)
        df["SMA20"] = df["Close"].rolling(20).mean()
        df["SMA50"] = df["Close"].rolling(50).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()

        # Golden/Death cross
        df["golden_cross"] = (df["SMA50"] > df["SMA200"]) & (
            df["SMA50"].shift(1) <= df["SMA200"].shift(1)
        )
        df["death_cross"] = (df["SMA50"] < df["SMA200"]) & (
            df["SMA50"].shift(1) >= df["SMA200"].shift(1)
        )

        # RSI (14)
        df["RSI"] = self.calculate_rsi(df["Close"], 14)

        # Volume (20-day avg of previous completed sessions — today excluded from its own baseline)
        df["vol_avg20"] = df["Volume"].shift(1).rolling(20).mean()
        df["vol_ratio"] = df["Volume"] / df["vol_avg20"]

        # ATR (14)
        df["ATR"] = self.calculate_atr(df, 14)

        # Price levels
        df["high_3d"] = df["High"].rolling(3).max()
        df["low_3d"] = df["Low"].rolling(3).min()

        # Market cap proxy: penny if price < 5
        df["is_penny"] = df["Close"] < 5

        df["support"] = df["Low"].tail(30).min()
        df["resistance"] = df["High"].tail(30).max()


        # MACD (12, 26, 9)
        df['ema12'] = df['Close'].ewm(span=12).mean()
        df['ema26'] = df['Close'].ewm(span=26).mean()
        df['macd'] = df['ema12'] - df['ema26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # MACD signals
        df['macd_bullish'] = (df['macd'] > df['macd_signal']) & (df['macd'].shift(1) <= df['macd_signal'].shift(1))
        df['macd_bearish'] = (df['macd'] < df['macd_signal']) & (df['macd'].shift(1) >= df['macd_signal'].shift(1))
        
        # Bollinger Bands (20, 2)
        df['bb_middle'] = df['Close'].rolling(20).mean()
        bb_std = df['Close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        
        # BB position (% from lower to upper band)
        df['bb_position'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # BB signals
        df['bb_squeeze'] = df['bb_width'] < 0.1  # Low volatility
        df['bb_upper_break'] = df['Close'] > df['bb_upper']
        df['bb_lower_break'] = df['Close'] < df['bb_lower']
        
        return df

    def classify_candle(self, df: pd.DataFrame) -> pd.Series:
        """Classify candles per your criteria."""
        range_safe = df["range"].replace(0, np.nan)

        lower_wick_ratio = (df["lower_wick"] / range_safe).fillna(0)
        upper_wick_ratio = (df["upper_wick"] / range_safe).fillna(0)

        conditions = [
            # Strong bullish
            (df["Close"] > df["Open"])
            & (df["body_size"] >= 1.5)
            & (df["body_pct"] >= 0.7)
            & (lower_wick_ratio <= 0.2),
            # Moderate bullish
            (df["Close"] > df["Open"])
            & (df["body_size"] >= 0.75)
            & (df["body_pct"] >= 0.5),
            # Strong bearish
            (df["Close"] < df["Open"])
            & (df["body_size"] >= 1.5)
            & (df["body_pct"] >= 0.7)
            & (upper_wick_ratio <= 0.2),
            # Moderate bearish
            (df["Close"] < df["Open"])
            & (df["body_size"] >= 0.75)
            & (df["body_pct"] >= 0.5),
        ]

        choices = [
            "strong_bullish",
            "moderate_bullish",
            "strong_bearish",
            "moderate_bearish",
        ]

        return pd.Series(
            np.select(conditions, choices, default="neutral"), index=df.index
        )

    def calculate_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """RSI calculation."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(0)

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average True Range."""
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()

        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=period).mean()
        return atr

    def _to_json_safe(self, row: pd.Series) -> dict:
        """Convert pandas Series with NumPy types to JSON-safe dict."""
        result = {}
        for key, value in row.items():
            if pd.isna(value):
                result[key] = None
            elif isinstance(value, (np.integer, np.int64, np.int32)):
                result[key] = int(value)
            elif isinstance(value, (np.floating, np.float64, np.float32)):
                result[key] = float(value)
            elif isinstance(value, np.bool_):
                result[key] = bool(value)
            else:
                result[key] = value
        return result


_yahoo_client: Optional[YahooClient] = None


def get_yahoo_client() -> YahooClient:
    global _yahoo_client
    if _yahoo_client is None:
        _yahoo_client = YahooClient()
    return _yahoo_client


def main():
    yahoo = YahooClient()
    x = yahoo.process_trading_data("AZTR")
    print(x)
    pass

if __name__ == "__main__":
    main()