from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
)
from alpaca.trading.requests import ClosePositionRequest
from alpaca.trading.models import Order, Position  # type hints only


@dataclass
class BrokerConfig:
    api_key: str
    api_secret: str
    paper: bool = True  # True = paper trading, False = live


class AlpacaBrokerClient:
    """
    Thin wrapper around Alpaca TradingClient.
    Exposes simple methods used by the agent/risk engine.
    """

    def __init__(self, config: Optional[BrokerConfig] = None) -> None:
        if config is None:
            # Default: load from environment variables
            config = BrokerConfig(
                api_key=os.environ["ALPACA_API_KEY"],
                api_secret=os.environ["ALPACA_API_SECRET"],
                paper=os.getenv("ALPACA_PAPER", "true").lower() == "true",
            )

        self.config = config
        self.client = TradingClient(
            api_key=config.api_key,
            secret_key=config.api_secret,
            paper=config.paper,
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
            # Alpaca raises if no position
            return None

    def list_open_orders(self) -> List[Dict[str, Any]]:
        orders = self.client.get_orders()
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
        """
        Simple market order.
        Either qty or notional must be provided.
        """
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
        """
        Simple limit order.
        """
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
        """
        Stop order (stop market).
        """
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
        """
        Stop-limit order.
        """
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
        """
        Bracket order: entry + TP + SL.
        Implemented using order_class='bracket' via classic trade API style.
        If you prefer pure alpaca-py OrderRequest types for brackets, adapt accordingly.
        """
        # For bracket, use the trading_client.submit_order keyword style
        order = self.client.submit_order(
            symbol=symbol,
            qty=qty,
            side=self._side_from_str(side),
            type=OrderType.MARKET if entry_type == "market" else OrderType.LIMIT,
            time_in_force=self._tif_from_str(time_in_force),
            limit_price=entry_price if entry_type == "limit" else None,
            order_class="bracket",
            take_profit={"limit_price": take_profit_price},
            stop_loss={"stop_price": stop_loss_price},
        )
        return order.__dict__

    # --------- Position closing / emergency controls ---------

    def close_position(
        self,
        symbol: str,
        percentage: Optional[float] = None,
        qty: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Close an open position (full or partial).
        If percentage is provided (0-100), close that percent.
        If qty is provided, close that quantity.
        If neither provided, close full position.
        """
        close_req = ClosePositionRequest()
        if percentage is not None:
            close_req.percentage = percentage
        if qty is not None:
            close_req.qty = qty

        order = self.client.close_position(symbol_or_asset_id=symbol, close_options=close_req)
        return order.__dict__

    def close_all_positions(self, cancel_orders: bool = True) -> List[Dict[str, Any]]:
        """
        Liquidate all open positions, optionally cancelling open orders first.
        """
        res = self.client.close_all_positions(cancel_orders=cancel_orders)
        # close_all_positions may return list/dict depending on SDK version, normalize to list of dicts
        if isinstance(res, dict):
            return [res]
        return [r for r in res]

    # --------- Convenience helpers for your agent ---------

    def get_equity_and_cash(self) -> Dict[str, float]:
        """
        Small helper for risk engine: returns {equity, cash}.
        """
        acct = self.client.get_account()
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
        }

    def is_trading_blocked(self) -> bool:
        """
        Check if account is currently blocked from trading.
        """
        acct = self.client.get_account()
        return bool(acct.trading_blocked)

