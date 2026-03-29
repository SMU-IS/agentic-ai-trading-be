"""
Backtest: candle-signal strategy with conservative / aggressive risk profiling.

Signal:    candle_type derived from daily OHLCV (bullish → BUY, bearish → SELL)
Risk adj:  risk_evaluation_metrics() applied per profile — same logic as live agent
Outcome:   forward-simulate up to MAX_HOLD_DAYS to check if TP or SL is hit first

Usage (run from trading-agent-m/):
    python -m app.backtest.backtest --ticker AAPL --start 2024-01-01 --end 2025-01-01 --account 10000
"""

import argparse
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from app.agents.nodes.risk_adjust import risk_evaluation_metrics
from app.agents.state import (
    RiskProfile,
    TradingDecision,
    TradeAction,
    YahooTechnicalData,
)

# -- Config --------------------------------------------------------------------
MAX_HOLD_DAYS   = 10       # force-exit after N days if neither TP nor SL hit
DEFAULT_ACCOUNT = 10_000.0


# -- Indicator computation -----------------------------------------------------

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # SMA
    df["sma20"]  = df["Close"].rolling(20).mean()
    df["sma50"]  = df["Close"].rolling(50).mean()
    df["sma200"] = df["Close"].rolling(200).mean()

    # ATR14 (Wilder smoothing)
    hl  = df["High"] - df["Low"]
    hc  = (df["High"] - df["Close"].shift()).abs()
    lc  = (df["Low"]  - df["Close"].shift()).abs()
    tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["atr14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    # RSI14
    delta = df["Close"].diff()
    gain  = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = (100 - (100 / (1 + gain / loss.replace(0, np.nan)))).fillna(50)

    # MACD (12/26/9)
    macd            = _ema(df["Close"], 12) - _ema(df["Close"], 26)
    sig             = _ema(macd, 9)
    df["macd"]           = macd
    df["macd_signal"]    = sig
    df["macd_histogram"] = macd - sig
    df["macd_bullish"]   = (macd > sig) & (macd.shift() <= sig.shift())
    df["macd_bearish"]   = (macd < sig) & (macd.shift() >= sig.shift())

    # Bollinger Bands (20, 2σ)
    std             = df["Close"].rolling(20).std()
    df["bb_middle"]      = df["sma20"]
    df["bb_upper"]       = df["sma20"] + 2 * std
    df["bb_lower"]       = df["sma20"] - 2 * std
    df["bb_width"]       = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
    df["bb_position"]    = (df["Close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
    df["bb_squeeze"]     = df["bb_width"] < df["bb_width"].rolling(20).mean() * 0.7
    df["bb_upper_break"] = df["Close"] > df["bb_upper"]
    df["bb_lower_break"] = df["Close"] < df["bb_lower"]

    # Volume ratio vs 20-day average
    df["vol_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()

    # Golden / death cross
    df["golden_cross"] = (df["sma50"] > df["sma200"]) & (df["sma50"].shift() <= df["sma200"].shift())
    df["death_cross"]  = (df["sma50"] < df["sma200"]) & (df["sma50"].shift() >= df["sma200"].shift())

    # 3-day range
    df["high_3d"] = df["High"].rolling(3).max()
    df["low_3d"]  = df["Low"].rolling(3).min()

    # Support / resistance: rolling 252-day min/max
    df["support"]    = df["Low"].rolling(252).min()
    df["resistance"] = df["High"].rolling(252).max()

    return df


# -- Candle classification -----------------------------------------------------

def _candle_type(row: pd.Series) -> str:
    o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
    rng = h - l
    if rng == 0:
        return "neutral"
    body_pct = abs(c - o) / rng
    is_bull  = c > o

    if body_pct < 0.1:
        return "doji"
    if body_pct >= 0.6:
        return "strong_bullish" if is_bull else "strong_bearish"
    if body_pct >= 0.3:
        return "moderate_bullish" if is_bull else "moderate_bearish"
    return "weak_bullish" if is_bull else "weak_bearish"


def candle_to_action(
    candle_type: str,
    sma50: Optional[float] = None,
    sma200: Optional[float] = None,
) -> Optional[TradeAction]:
    """
    Map candle_type to TradeAction with trend filter.
    Only BUY in uptrend (SMA50 > SMA200), only SELL in downtrend (SMA50 < SMA200).
    Weak candles and doji are always skipped.
    """
    in_uptrend   = (sma50 is not None and sma200 is not None and sma50 > sma200)
    in_downtrend = (sma50 is not None and sma200 is not None and sma50 < sma200)

    if candle_type in ("strong_bullish", "moderate_bullish") and in_uptrend:
        return TradeAction.BUY
    if candle_type in ("strong_bearish", "moderate_bearish") and in_downtrend:
        return TradeAction.SELL
    return None


# -- Data conversion -----------------------------------------------------------

def row_to_yahoo(row: pd.Series, period_summary: str = "") -> YahooTechnicalData:
    o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
    rng = h - l or 1.0

    def _f(key: str, default: float = 0.0) -> float:
        val = row.get(key)
        return float(val) if pd.notna(val) else default

    def _b(key: str) -> bool:
        return bool(row.get(key, False))

    return YahooTechnicalData(
        current_price  = float(c),
        open           = float(o),
        high           = float(h),
        low            = float(l),
        close          = float(c),
        adj_close      = float(c),
        volume         = int(row["Volume"]),
        candle_type    = _candle_type(row),
        body_size      = round(abs(c - o) / o * 100, 3),
        body_pct       = round(abs(c - o) / rng, 3),
        upper_wick     = round((h - max(o, c)) / c * 100, 3),
        lower_wick     = round((min(o, c) - l)  / c * 100, 3),
        rsi            = _f("rsi", 50.0),
        vol_ratio      = _f("vol_ratio", 1.0),
        atr14          = _f("atr14", c * 0.01),
        sma20          = _f("sma20")  if pd.notna(row.get("sma20"))  else None,
        sma50          = _f("sma50")  if pd.notna(row.get("sma50"))  else None,
        sma200         = _f("sma200") if pd.notna(row.get("sma200")) else None,
        golden_cross   = _b("golden_cross"),
        death_cross    = _b("death_cross"),
        high_3d        = _f("high_3d", h),
        low_3d         = _f("low_3d",  l),
        is_penny       = float(c) < 5.0,
        support        = _f("support",    l),
        resistance     = _f("resistance", h),
        period_summary = period_summary,
        macd           = _f("macd"),
        macd_signal    = _f("macd_signal"),
        macd_histogram = _f("macd_histogram"),
        macd_bullish   = _b("macd_bullish"),
        macd_bearish   = _b("macd_bearish"),
        bb_upper       = _f("bb_upper", h),
        bb_middle      = _f("bb_middle", c),
        bb_lower       = _f("bb_lower", l),
        bb_width       = _f("bb_width"),
        bb_position    = _f("bb_position", 0.5),
        bb_squeeze     = _b("bb_squeeze"),
        bb_upper_break = _b("bb_upper_break"),
        bb_lower_break = _b("bb_lower_break"),
    )


# -- Confidence heuristic ------------------------------------------------------

def _derive_confidence(yahoo: YahooTechnicalData, action: TradeAction) -> float:
    """Indicator-based confidence score (replicates what the LLM would produce)."""
    score   = 0.75
    is_sell = action == TradeAction.SELL

    if is_sell and yahoo.macd_bearish:   score += 0.05
    elif not is_sell and yahoo.macd_bullish: score += 0.05

    if is_sell and yahoo.rsi > 65:       score += 0.05
    elif not is_sell and yahoo.rsi < 35: score += 0.05

    if yahoo.vol_ratio >= 1.5:           score += 0.05
    elif yahoo.vol_ratio < 0.5:          score -= 0.05

    if "strong" in yahoo.candle_type:    score += 0.05
    elif "weak" in yahoo.candle_type:    score -= 0.05

    return round(min(max(score, 0.0), 1.0), 2)


# -- Trade simulation ----------------------------------------------------------

def simulate_outcome(
    df:        pd.DataFrame,
    entry_idx: int,
    tp:        float,
    sl:        float,
    action:    TradeAction,
) -> tuple[str, float, int]:
    """
    Walk forward day-by-day checking High/Low against TP and SL.
    Returns: ("TP" | "SL" | "EXPIRED", exit_price, days_held)
    """
    is_buy = action == TradeAction.BUY

    for offset in range(1, MAX_HOLD_DAYS + 1):
        fwd_idx = entry_idx + offset
        if fwd_idx >= len(df):
            break
        fwd = df.iloc[fwd_idx]

        if is_buy:
            if fwd["High"] >= tp:  return "TP", tp, offset
            if fwd["Low"]  <= sl:  return "SL", sl, offset
        else:
            if fwd["Low"]  <= tp:  return "TP", tp, offset
            if fwd["High"] >= sl:  return "SL", sl, offset

    exit_idx   = min(entry_idx + MAX_HOLD_DAYS, len(df) - 1)
    exit_price = float(df.iloc[exit_idx]["Close"])
    return "EXPIRED", exit_price, min(MAX_HOLD_DAYS, len(df) - 1 - entry_idx)


# -- Backtest engine -----------------------------------------------------------

def run_backtest(ticker: str, start: str, end: str, account_bp: float) -> None:
    print(f"\n{'='*62}")
    print(f"  BACKTEST  {ticker}  |  {start} to {end}  |  BP=${account_bp:,.0f}")
    print(f"{'='*62}\n")

    # -- Download + prepare ----------------------------------------
    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if raw.empty:
        print(f"❌  No data returned for {ticker}")
        return

    # yfinance sometimes returns MultiIndex columns
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [c.title() for c in raw.columns]

    df = compute_indicators(raw).dropna(subset=["sma50", "atr14", "rsi"])
    print(f"   Loaded {len(df)} trading days after indicator warmup\n")

    period  = f"{df.index[0].date()} - {df.index[-1].date()} ({len(df)} trading days)"
    results = {RiskProfile.CONSERVATIVE: [], RiskProfile.AGGRESSIVE: []}

    # -- Signal + risk eval loop -----------------------------------
    for i, (date, row) in enumerate(df.iterrows()):
        yahoo  = row_to_yahoo(row, period_summary=period)
        action = candle_to_action(yahoo.candle_type, yahoo.sma50, yahoo.sma200)
        if action is None:
            continue

        confidence = _derive_confidence(yahoo, action)
        entry      = float(row["Close"])

        # Placeholder SL/TP — overridden by risk_evaluation_metrics
        sl_placeholder = entry * (0.97 if action == TradeAction.BUY else 1.03)
        tp_placeholder = entry * (1.06 if action == TradeAction.BUY else 0.94)

        trade = TradingDecision(
            action              = action,
            confidence          = confidence,
            entry_price         = entry,
            stop_loss           = sl_placeholder,
            take_profit         = tp_placeholder,
            qty                 = 1.0,
            risk_reward         = "2:1",
            thesis              = f"Candle signal: {yahoo.candle_type}",
            current_stock_price = entry,
            ticker              = ticker,
        )

        for profile in [RiskProfile.CONSERVATIVE, RiskProfile.AGGRESSIVE]:
            assessment = risk_evaluation_metrics(trade, yahoo, account_bp, profile)
            adj        = assessment.adjusted_trade

            if assessment.risk_status in ("BLOCKED", "REVIEW") or adj.qty == 0:
                results[profile].append({
                    "date":    date, "action":  action.value,
                    "candle":  yahoo.candle_type, "outcome": assessment.risk_status,
                    "pnl": 0.0, "days": 0, "rr": 0.0, "score": assessment.risk_score,
                })
                continue

            outcome, exit_price, days = simulate_outcome(df, i, adj.take_profit, adj.stop_loss, action)

            pnl = (
                (exit_price - adj.entry_price) * adj.qty if action == TradeAction.BUY
                else (adj.entry_price - exit_price) * adj.qty
            )

            try:
                rr = float(assessment.metrics.actual_rr.split(":")[0])
            except (ValueError, AttributeError):
                rr = 0.0

            results[profile].append({
                "date":    date,
                "action":  action.value,
                "candle":  yahoo.candle_type,
                "outcome": outcome,
                "pnl":     round(pnl, 2),
                "days":    days,
                "rr":      rr,
                "score":   assessment.risk_score,
                "entry":   adj.entry_price,
                "tp":      adj.take_profit,
                "sl":      adj.stop_loss,
                "qty":     adj.qty,
            })

    # -- Report ----------------------------------------------------
    for profile in [RiskProfile.CONSERVATIVE, RiskProfile.AGGRESSIVE]:
        trades  = results[profile]
        active  = [t for t in trades if t["outcome"] not in ("BLOCKED", "REVIEW")]
        blocked = [t for t in trades if t["outcome"] == "BLOCKED"]
        reviewed = [t for t in trades if t["outcome"] == "REVIEW"]
        wins    = [t for t in active  if t["outcome"] == "TP"]
        losses  = [t for t in active  if t["outcome"] == "SL"]
        expired = [t for t in active  if t["outcome"] == "EXPIRED"]

        total_pnl = sum(t["pnl"] for t in active)
        win_rate  = len(wins) / len(active) * 100 if active else 0.0
        avg_days  = sum(t["days"] for t in active) / len(active) if active else 0.0
        avg_rr    = sum(t["rr"]   for t in active) / len(active) if active else 0.0
        avg_score = sum(t["score"] for t in active) / len(active) if active else 0.0

        print(f"{'-'*62}")
        print(f"  {profile.value.upper()} PROFILE")
        print(f"{'-'*62}")
        print(f"  Total signals    : {len(trades)}")
        print(f"  Blocked          : {len(blocked)}")
        print(f"  Skipped (REVIEW) : {len(reviewed)}")
        print(f"  Executed trades  : {len(active)}")
        print(f"  |-- TP  (wins)    : {len(wins)}")
        print(f"  |-- SL  (losses)  : {len(losses)}")
        print(f"  +-- Expired       : {len(expired)}")
        print(f"  Win rate         : {win_rate:.1f}%")
        print(f"  Total P&L        : ${total_pnl:>10,.2f}")
        print(f"  Avg hold (days)  : {avg_days:.1f}")
        print(f"  Avg R:R          : {avg_rr:.2f}")
        print(f"  Avg risk score   : {avg_score:.3f}")
        print()

        # Breakdown by candle type
        candle_stats: dict[str, dict] = {}
        for t in active:
            ct = t["candle"]
            candle_stats.setdefault(ct, {"total": 0, "wins": 0, "pnl": 0.0})
            candle_stats[ct]["total"] += 1
            if t["outcome"] == "TP":
                candle_stats[ct]["wins"] += 1
            candle_stats[ct]["pnl"] += t["pnl"]

        print(f"  {'Candle Type':<25} {'Trades':>7} {'Win%':>7} {'P&L':>12}")
        print(f"  {'-'*54}")
        for ct, s in sorted(candle_stats.items(), key=lambda x: -x[1]["pnl"]):
            wr = s["wins"] / s["total"] * 100 if s["total"] else 0
            print(f"  {ct:<25} {s['total']:>7} {wr:>6.0f}% {s['pnl']:>12,.2f}")
        print()

    print(f"{'='*62}\n")


# -- CLI -----------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Candle-signal backtest with risk profiling")
    parser.add_argument("--ticker",  default="AAPL",       help="Stock ticker (default: AAPL)")
    parser.add_argument("--start",   default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",     default="2025-01-01", help="End date YYYY-MM-DD")
    parser.add_argument("--account", default=10_000.0, type=float, help="Simulated buying power")
    args = parser.parse_args()

    run_backtest(
        ticker     = args.ticker,
        start      = args.start,
        end        = args.end,
        account_bp = args.account,
    )
