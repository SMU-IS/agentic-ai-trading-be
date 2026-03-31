import requests
from typing import Optional, Dict, Any
from src.config import settings
from src.models.state import DeepAnalysis

TELEGRAM_URL = f"{settings.aggregator_base_url}/telegram/signal"


def post_signal_to_telegram(signal: DeepAnalysis) -> Optional[Dict[str, Any]]:
    """
    POST a DeepAnalysis signal to the trading-service Telegram endpoint.

    Returns the response JSON or None if failed.
    """
    payload = signal.to_dict()

    try:
        print(f"   [📡 Telegram] Posting signal | {signal.ticker} {signal.trade_signal.value}")
        resp = requests.post(TELEGRAM_URL, json=payload, timeout=10)

        if resp.status_code == 200:
            print(f"   [✅ Telegram] Signal posted | {signal.ticker}")
            return resp.json()

        print(f"   [❌ Telegram] Failed {resp.status_code} | {resp.text}")
        return None

    except requests.exceptions.ConnectionError as e:
        print(f"   [❌ Telegram] ConnectionError — cannot reach trading-service: {e}")
        return None
    except requests.exceptions.Timeout:
        print(f"   [❌ Telegram] Timeout — trading-service did not respond")
        return None
    except Exception as e:
        print(f"   [❌ Telegram] Unexpected error: {e}")
        return None
