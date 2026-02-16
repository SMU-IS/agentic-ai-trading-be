import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
)
from alpaca.data.timeframe import (
    TimeFrame,  # TimeFrame.from_string for "1Day" etc. [web:19][web:166]
)
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import (
    OrderClass,
    OrderSide,
    QueryOrderStatus,
    TimeInForce,
)
from alpaca.trading.models import Order, Position  # type hints only
from alpaca.trading.requests import (
    ClosePositionRequest,
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopLossRequest,
    StopOrderRequest,
    TakeProfitRequest,
)


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
        raise RuntimeError(
            "Missing ALPACA_API_KEY or ALPACA_API_SECRET in environment."
        )

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
        extended_hours: bool = True,
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
            extended_hours=extended_hours,
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

        order = self.client.close_position(
            symbol_or_asset_id=symbol, close_options=close_req
        )
        return order.__dict__

    def close_all_positions(self, cancel_orders: bool = True) -> List[Dict[str, Any]]:
        res = self.client.close_all_positions(cancel_orders=cancel_orders)
        if isinstance(res, dict):
            return [res]
        return [r for r in res]

    def cancel_orders(
        self, order_ids: Optional[List[str]] = None, cancel_all: bool = False
    ) -> Dict[str, Any]:
        """
        Cancel one or more open orders by ID, or cancel all open orders.

        Args:
            order_ids: List of order IDs to cancel (e.g., ["abc-123", "def-456"])
            cancel_all: If True, cancels ALL open orders (ignores order_ids)

        Returns:
            Dict with success/failure results for each order
        """
        if cancel_all:
            try:
                # Cancel all open orders at once
                cancelled = self.client.cancel_orders()
                return {
                    "status": "success",
                    "message": "All open orders cancelled",
                    "cancelled_count": len(cancelled) if cancelled else 0,
                    "details": [order.__dict__ for order in cancelled]
                    if cancelled
                    else [],
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Failed to cancel all orders: {str(e)}",
                }

        if not order_ids:
            raise ValueError("Must provide order_ids or set cancel_all=True")

        # Cancel specific orders
        results = {"success": [], "failed": [], "total": len(order_ids)}

        for order_id in order_ids:
            try:
                self.client.cancel_order_by_id(order_id)
                results["success"].append({"order_id": order_id, "status": "cancelled"})
            except Exception as e:
                results["failed"].append({"order_id": order_id, "error": str(e)})

        results["success_count"] = len(results["success"])
        results["failed_count"] = len(results["failed"])

        return results

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
        bars = self.data_client.get_stock_bars(
            req
        )  # returns data mapping symbol -> Bars. [web:158]

        if symbol in bars:
            bar_list = bars[
                symbol
            ].to_dicts()  # list[dict] with timestamp, open, high, low, close, volume
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
                "tape": str(trade.tape) if trade.tape else None,
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
                "tape": quote.tape,
            }
        except Exception as e:
            return {"error": str(e)}

    # --------- Portfolio history ---------
    def get_portfolio_history(
        self,
    ) -> Dict[str, Any]:
        """
        Get portfolio performance history using Alpaca TradingClient.
        """
        try:
            history = self.client.get_portfolio_history()

            historical = []
            for i, ts in enumerate(history.timestamp):
                historical.append(
                    {
                        "date": datetime.fromtimestamp(ts).isoformat() + "Z"
                        if isinstance(ts, (int, float))
                        else f"{ts}Z",
                        "value": float(history.equity[i]),  # Use equity as main value
                    }
                )

            return {"historical": historical}

        except Exception as e:
            return {"error": f"Portfolio history failed: {str(e)}"}

    # Check for conflicting positions
    # ---------------------------------
    def check_conflicting_positions(
        self, symbol: str, intended_side: str, intended_qty: float
    ) -> Dict[str, Any]:
        """
        Check for conflicting positions and orders that need cleanup.
        """
        try:
            # Get current position
            current_position = None
            try:
                current_position = self.client.get_open_position(symbol)
            except Exception:
                pass  # No position exists

            # ✅ FIXED: Use GetOrdersRequest object
            order_filter = GetOrdersRequest(
                status=QueryOrderStatus.OPEN, symbols=[symbol]
            )
            open_orders = self.client.get_orders(filter=order_filter)

            conflicts = {
                "has_conflict": False,
                "symbol": symbol,
                "intended_side": intended_side,
                "intended_qty": intended_qty,
                "current_position": None,
                "conflicting_orders": [],
                "actions_required": [],
            }

            # Check position conflict
            if current_position:
                position_qty = float(current_position.qty)
                position_side = "long" if position_qty > 0 else "short"

                conflicts["current_position"] = {
                    "qty": position_qty,
                    "side": position_side,
                    "avg_entry_price": float(current_position.avg_entry_price),
                    "market_value": float(current_position.market_value),
                    "unrealized_pl": float(current_position.unrealized_pl),
                }

                # Conflict: trying to SELL when LONG or BUY when SHORT
                if (intended_side.lower() == "sell" and position_qty > 0) or (
                    intended_side.lower() == "buy" and position_qty < 0
                ):
                    conflicts["has_conflict"] = True
                    conflicts["actions_required"].append(
                        {
                            "action": "close_position",
                            "symbol": symbol,
                            "current_qty": position_qty,
                            "reason": f"Cannot {intended_side.upper()} while holding {position_side.upper()} position",
                        }
                    )

            # Check conflicting orders
            if open_orders:
                for order in open_orders:
                    order_dict = {
                        "order_id": str(order.id),
                        "side": order.side.value,
                        "qty": float(order.qty) if order.qty else None,
                        "order_type": order.order_type.value,
                        "status": order.status.value,
                        "order_class": order.order_class.value
                        if order.order_class
                        else None,
                    }
                    conflicts["conflicting_orders"].append(order_dict)

                conflicts["has_conflict"] = True
                conflicts["actions_required"].append(
                    {
                        "action": "cancel_orders",
                        "order_ids": [str(order.id) for order in open_orders],
                        "count": len(open_orders),
                        "reason": f"Cancel {len(open_orders)} pending orders for {symbol}",
                    }
                )

            return conflicts

        except Exception as e:
            return {"error": str(e), "symbol": symbol}

    # Resolve conflicts by closing positions and cancelling orders
    # -----------------------------------------------------------------
    def resolve_conflicts(
        self,
        symbol: str,
        intended_side: str,
        intended_qty: float,
        auto_resolve: bool = True,
    ) -> Dict[str, Any]:
        """
        Resolve conflicts: CANCEL ORDERS FIRST → CLOSE POSITION → Clean slate.
        """
        # Step 1: Check conflicts
        conflicts = self.check_conflicting_positions(
            symbol, intended_side, intended_qty
        )

        if not conflicts.get("has_conflict"):
            return {
                "status": "no_conflict",
                "symbol": symbol,
                "message": "No conflicts found - ready to trade",
            }

        if not auto_resolve:
            return {
                "status": "conflict_detected",
                "conflicts": conflicts,
                "message": "Conflicts found but auto_resolve=False",
            }

        # Step 2: Auto-resolve (ORDERS FIRST → POSITION)
        resolution_results = {
            "status": "resolved",
            "symbol": symbol,
            "actions_taken": [],
            "conflicts_detected": conflicts,
        }

        # ✅ ORDER 1: Cancel pending orders FIRST
        for action in conflicts.get("actions_required", []):
            if action["action"] == "cancel_orders":
                try:
                    cancel_result = self.cancel_orders(order_ids=action["order_ids"])
                    resolution_results["actions_taken"].append(
                        {
                            "action": "cancelled_orders",
                            "order_ids": action["order_ids"],
                            "count": cancel_result.get("success_count", 0),
                            "status": "success",
                        }
                    )
                    print(
                        f"   [✅ CANCELLED] {cancel_result.get('success_count', 0)} orders for {symbol}"
                    )
                except Exception as e:
                    resolution_results["actions_taken"].append(
                        {
                            "action": "cancel_orders_failed",
                            "order_ids": action["order_ids"],
                            "error": str(e),
                        }
                    )
                    print(f"   [❌ CANCEL FAILED] {str(e)}")

        # ✅ ORDER 2: Close position SECOND (after orders cancelled)
        for action in conflicts.get("actions_required", []):
            if action["action"] == "close_position":
                try:
                    close_result = self.client.close_position(symbol)
                    resolution_results["actions_taken"].append(
                        {
                            "action": "closed_position",
                            "symbol": symbol,
                            "qty_closed": action["current_qty"],
                            "order_id": str(close_result.id) if close_result else None,
                            "status": "success",
                        }
                    )
                    print(
                        f"   [✅ CLOSED] {symbol} position ({action['current_qty']} shares)"
                    )
                except Exception as e:
                    resolution_results["actions_taken"].append(
                        {
                            "action": "close_position_failed",
                            "symbol": symbol,
                            "qty_closed": action["current_qty"],
                            "error": str(e),
                        }
                    )
                    print(f"   [❌ CLOSE FAILED] {str(e)}")

        # Step 3: Verify clean slate
        verification = self.verify_clean_slate(symbol)
        resolution_results["verification"] = verification

        return resolution_results

    def verify_clean_slate(self, symbol: str) -> Dict[str, Any]:
        """
        Verify no positions or open orders remain for symbol.
        """
        try:
            # Check position
            try:
                self.client.get_open_position(symbol)
                position_status = "position_exists"
            except Exception as e:
                position_status = f"no_position {e}"

            # Check orders
            order_filter = GetOrdersRequest(
                status=QueryOrderStatus.OPEN, symbols=[symbol]
            )
            open_orders = self.client.get_orders(filter=order_filter)
            orders_status = "orders_exist" if open_orders else "no_orders"

            return {
                "symbol": symbol,
                "position_status": position_status,
                "orders_status": orders_status,
                "ready_to_trade": position_status == "no_position"
                and orders_status == "no_orders",
            }
        except Exception as e:
            return {"error": str(e), "symbol": symbol}
