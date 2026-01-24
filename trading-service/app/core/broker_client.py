import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import (
    OrderSide,
    TimeInForce,
    OrderType,
    QueryOrderStatus,
    OrderClass,
)
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
    ClosePositionRequest,
    GetOrdersRequest,
    TakeProfitRequest,
    StopLossRequest,
)
from alpaca.trading.models import Order, Position  # type hints only

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame  # TimeFrame.from_string for "1Day" etc. [web:19][web:166]

@dataclass
class BrokerConfig:
    api_key: str
    api_secret: str
    paper: bool = True  # True = paper trading, False = live


def _load_config_from_env() -> BrokerConfig:
    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_API_SECRET")
    paper_flag = os.getenv("ALPACA_PAPER", "true").lower() == "true"

    if not api_key or not api_secret:
        raise RuntimeError("Missing ALPACA_API_KEY or ALPACA_API_SECRET in environment.")

    return BrokerConfig(
        api_key=api_key,
        api_secret=api_secret,
        paper=paper_flag,
    )


def create_broker_client() -> "AlpacaBrokerClient":
    """
    Factory used by FastAPI dependency injection.
    """
    cfg = _load_config_from_env()
    return AlpacaBrokerClient(cfg)


class AlpacaBrokerClient:
    """
    Thin wrapper around Alpaca TradingClient and StockHistoricalDataClient.
    Exposes simple methods used by the agent/risk engine and FastAPI layer.
    """

    def __init__(self, config: Optional[BrokerConfig] = None) -> None:
        if config is None:
            config = _load_config_from_env()

        self.config = config

        # Trading (orders, positions, account)
        self.client = TradingClient(
            api_key=config.api_key,
            secret_key=config.api_secret,
            paper=config.paper,
        )

        # Market data (historical stock bars) [web:158][web:166]
        self.data_client = StockHistoricalDataClient(
            api_key=config.api_key,
            secret_key=config.api_secret,
        )

    # --------- Account / positions / orders ---------

    def get_account(self) -> Dict[str, Any]:
        account = self.client.get_account()
        return account.__dict__

    def get_open_positions(self) -> List[Dict[str, Any]]:
        positions = self.client.get_all_positions()
        return [p.__dict__ for p in positions]

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            pos: Position = self.client.get_open_position(symbol)
            return pos.__dict__
        except Exception:
            return None

    def list_open_orders(self) -> List[Dict[str, Any]]:
        # Explicit OPEN status and nested legs [web:143][web:145]
        req = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            nested=True,
        )
        orders = self.client.get_orders(filter=req)
        return [o.__dict__ for o in orders]

    def list_all_orders(self, limit: int = 200) -> List[Dict[str, Any]]:
        # ALL: both open and closed orders; limit per Alpaca docs [web:143][web:153]
        req = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=limit,
            nested=True,
        )
        orders = self.client.get_orders(filter=req)
        return [o.__dict__ for o in orders]

    def get_order(self, order_id: str) -> Dict[str, Any]:
        order: Order = self.client.get_order_by_id(order_id)
        return order.__dict__

    # --------- Order creation helpers ---------

    def _side_from_str(self, side: str) -> OrderSide:
        side = side.lower()
        if side == "buy":
            return OrderSide.BUY
        elif side == "sell":
            return OrderSide.SELL
        else:
            raise ValueError(f"Invalid side: {side}")

    def _tif_from_str(self, tif: str) -> TimeInForce:
        tif = tif.lower()
        mapping = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "opg": TimeInForce.OPG,
            "cls": TimeInForce.CLS,
            "ioc": TimeInForce.IOC,
            "fok": TimeInForce.FOK,
        }
        if tif not in mapping:
            raise ValueError(f"Unsupported time_in_force: {tif}")
        return mapping[tif]

    # --------- Public order methods ---------

    def submit_market_order(
        self,
        symbol: str,
        side: str,
        qty: Optional[float] = None,
        notional: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Dict[str, Any]:
        if qty is None and notional is None:
            raise ValueError("Either qty or notional must be specified")

        order_req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            notional=notional,
            side=self._side_from_str(side),
            time_in_force=self._tif_from_str(time_in_force),
        )
        order = self.client.submit_order(order_data=order_req)
        return order.__dict__

    def submit_limit_order(
        self,
        symbol: str,
        side: str,
        limit_price: float,
        qty: Optional[float] = None,
        notional: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Dict[str, Any]:
        if qty is None and notional is None:
            raise ValueError("Either qty or notional must be specified")

        order_req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            notional=notional,
            side=self._side_from_str(side),
            time_in_force=self._tif_from_str(time_in_force),
            limit_price=limit_price,
        )
        order = self.client.submit_order(order_data=order_req)
        return order.__dict__

    def submit_stop_order(
        self,
        symbol: str,
        side: str,
        stop_price: float,
        qty: Optional[float] = None,
        notional: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Dict[str, Any]:
        if qty is None and notional is None:
            raise ValueError("Either qty or notional must be specified")

        order_req = StopOrderRequest(
            symbol=symbol,
            qty=qty,
            notional=notional,
            side=self._side_from_str(side),
            time_in_force=self._tif_from_str(time_in_force),
            stop_price=stop_price,
        )
        order = self.client.submit_order(order_data=order_req)
        return order.__dict__

    def submit_stop_limit_order(
        self,
        symbol: str,
        side: str,
        stop_price: float,
        limit_price: float,
        qty: Optional[float] = None,
        notional: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Dict[str, Any]:
        if qty is None and notional is None:
            raise ValueError("Either qty or notional must be specified")

        order_req = StopLimitOrderRequest(
            symbol=symbol,
            qty=qty,
            notional=notional,
            side=self._side_from_str(side),
            time_in_force=self._tif_from_str(time_in_force),
            stop_price=stop_price,
            limit_price=limit_price,
        )
        order = self.client.submit_order(order_data=order_req)
        return order.__dict__

    def submit_bracket_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_type: str,
        entry_price: Optional[float],
        take_profit_price: float,
        stop_loss_price: float,
        time_in_force: str = "day",
    ) -> Dict[str, Any]:
        if entry_type not in ("market", "limit"):
            raise ValueError("entry_type must be 'market' or 'limit'")
        if entry_type == "limit" and entry_price is None:
            raise ValueError("entry_price required for limit entry")

        side_enum = self._side_from_str(side)
        tif_enum = self._tif_from_str(time_in_force)

        # Trading API requires NESTED objects
        take_profit = TakeProfitRequest(limit_price=take_profit_price)
        stop_loss = StopLossRequest(stop_price=stop_loss_price)

        kwargs = {
            "symbol": symbol,
            "qty": qty,
            "side": side_enum,
            "time_in_force": tif_enum,
            "order_class": OrderClass.BRACKET,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
        }

        if entry_type == "market":
            order_req = MarketOrderRequest(**kwargs)
        else:
            kwargs["limit_price"] = entry_price
            order_req = LimitOrderRequest(**kwargs)

        # Debug: Print JSON to verify
        print("Submitted JSON:", order_req.model_dump_json(indent=2))

        order = self.client.submit_order(order_data=order_req)
        return order.__dict__

    # --------- Position closing / emergency controls ---------

    def close_position(
        self,
        symbol: str,
        percentage: Optional[float] = None,
        qty: Optional[float] = None,
    ) -> Dict[str, Any]:
        close_req = ClosePositionRequest()
        if percentage is not None:
            close_req.percentage = percentage
        if qty is not None:
            close_req.qty = qty

        order = self.client.close_position(symbol_or_asset_id=symbol, close_options=close_req)
        return order.__dict__

    def close_all_positions(self, cancel_orders: bool = True) -> List[Dict[str, Any]]:
        res = self.client.close_all_positions(cancel_orders=cancel_orders)
        if isinstance(res, dict):
            return [res]
        return [r for r in res]

    # --------- Convenience helpers ---------

    def get_equity_and_cash(self) -> Dict[str, float]:
        acct = self.client.get_account()
        return {"equity": float(acct.equity), "cash": float(acct.cash)}

    def is_trading_blocked(self) -> bool:
        acct = self.client.get_account()
        return bool(acct.trading_blocked)

    # --------- Historical market data ---------

    def get_stock_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve historical OHLCV bars for a single stock symbol.

        timeframe examples: "1Min", "5Min", "15Min", "1Hour", "1Day". [web:158][web:166]
        """
        tf = TimeFrame.from_string(timeframe)

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=start,
            end=end,
            limit=limit,
        )
        bars = self.data_client.get_stock_bars(req)  # returns data mapping symbol -> Bars. [web:158]

        if symbol in bars:
            bar_list = bars[symbol].to_dicts()  # list[dict] with timestamp, open, high, low, close, volume
        else:
            bar_list = []

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": bar_list,
        }
    
    def get_latest_trade(self, symbol: str) -> Dict[str, Any]:
        """
        Get the most recent trade for a single symbol.
        """
        try:
            request = StockLatestTradeRequest(symbol_or_symbols=symbol)
            trades = self.data_client.get_stock_latest_trade(request)
            
            if symbol not in trades:
                return {"error": f"No trade data for {symbol}"}
            
            trade = trades[symbol]
            return {
                "symbol": symbol,
                "price": float(trade.price),
                "size": int(trade.size),
                "exchange": str(trade.exchange),
                "conditions": trade.conditions,
                "timestamp": trade.timestamp.isoformat() if trade.timestamp else None,
                "id": str(trade.id),
                "tape": str(trade.tape) if trade.tape else None
            }
        except Exception as e:
            return {"error": str(e)}
        
    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get the most recent quote for a single symbol.
        """
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = self.data_client.get_stock_latest_quote(request)
            
            if symbol not in quotes:
                return {"error": f"No quote data for {symbol}"}
            
            quote = quotes[symbol]
            return {
                "symbol": symbol,
                "bid_price": float(quote.bid_price),
                "bid_size": int(quote.bid_size),
                "ask_price": float(quote.ask_price),
                "ask_size": int(quote.ask_size),
                "timestamp": quote.timestamp.isoformat() if quote.timestamp else None,
                "conditions": quote.conditions,
                "tape": quote.tape
            }
        except Exception as e:
            return {"error": str(e)}
