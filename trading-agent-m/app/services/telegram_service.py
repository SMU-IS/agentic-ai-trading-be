import httpx
from typing import Optional, Dict, Any
from app.core.config import env_config

TELEGRAM_ORDER_URL = f"{env_config.trading_service_url}/telegram/order"


async def post_order_to_telegram(order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    POST an order result to the trading-service Telegram endpoint.
    """
    symbol = order.get("symbol", "N/A")
    status = order.get("status", "N/A")

    print(f"   [📬 Telegram] Posting order | {symbol} {status}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(TELEGRAM_ORDER_URL, json=order)

            if resp.status_code == 200:
                print(f"   [✅ Telegram] Order posted | {symbol}")
                return resp.json()

            print(f"   [❌ Telegram] Failed {resp.status_code} | {resp.text}")
            return None

        except httpx.ConnectError as e:
            print(f"   [❌ Telegram] ConnectError — cannot reach trading-service: {e}")
            return None
        except httpx.TimeoutException:
            print(f"   [❌ Telegram] Timeout — trading-service did not respond")
            return None
        except Exception as e:
            print(f"   [❌ Telegram] Unexpected error: {e}")
            return None
