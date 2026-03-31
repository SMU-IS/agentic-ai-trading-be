"""
Telegram notification service.
Posts trading signals and order results to dedicated supergroup topics.

Topics:
  Signals → https://t.me/c/3833243237/2  (thread_id=2)
  Orders  → https://t.me/c/3833243237/3  (thread_id=3)

Required env var: TELEGRAM_BOT_TOKEN
"""

import httpx
from app.config import settings

_CHAT_ID       = "-1003833243237"
_THREAD_SIGNAL = 2
_THREAD_ORDER  = 3
_API_BASE      = "https://api.telegram.org/bot{token}/sendMessage"


async def _send(text: str, thread_id: int) -> dict:
    url = _API_BASE.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id":           _CHAT_ID,
        "message_thread_id": thread_id,
        "text":              text,
        "parse_mode":        "HTML",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


# ── Public API ────────────────────────────────────────────────────────────────

async def post_signal(signal: dict) -> None:
    """
    Post a trading signal to the Signals topic.

    Expected keys: ticker, trade_signal, confidence (0-10), rumor_summary,
                   trade_rationale, credibility, credibility_reason,
                   references, position_size_pct, stop_loss_pct, target_pct
    """
    ticker      = signal.get("ticker", "N/A")
    action      = signal.get("trade_signal", signal.get("action", "N/A"))
    confidence  = signal.get("confidence", 0)          # 0–10 scale
    credibility = signal.get("credibility", "N/A")
    summary     = signal.get("rumor_summary", "")
    rationale   = signal.get("trade_rationale", "")
    cred_reason = signal.get("credibility_reason", "")
    pos_pct     = signal.get("position_size_pct", "N/A")
    sl_pct      = signal.get("stop_loss_pct", "N/A")
    tp_pct      = signal.get("target_pct", "N/A")
    refs        = signal.get("references") or []

    action_icon = "🟢" if str(action).upper() == "BUY" else "🔴" if str(action).upper() == "SELL" else "⚪"
    cred_icon = "🧠" if credibility == "High" else "🧐" if credibility == "Medium" else "⚠️"
    conf_icon   = "🔥" if confidence >= 8 else "✅" if confidence >= 6 else "⚠️" if confidence >= 4 else "❌"

    refs_text = "\n".join(f"  • {r}" for r in refs[:3]) if refs else "N/A"

    text = (
        f"{action_icon} <b>{action} Signal for  {ticker}</b>\n"
        f"{cred_icon} Credibility: <b>{credibility}</b>\n"
        f"{conf_icon} Confidence: <b>{confidence}/10</b>\n"

        f"\n💡 <b>Rumor Summary</b>\n"
        f"<i>{summary}</i>\n"

        f"\n🔍 <b>Confirmation</b>\n"
        f"<i>{rationale}</i>\n"
        f"<blockquote>{cred_reason}</blockquote>\n"

        f"\n🔗 <b>Sources</b>\n"
        f"{refs_text}"
    )
    await _send(text, _THREAD_SIGNAL)
    print(f"   [📡 Telegram] Signal posted | {ticker} {action}")


async def post_order(order: dict) -> None:
    """
    Post an order execution result to the Orders topic.
    """
    symbol     = order.get("symbol", "N/A")
    action     = order.get("action", order.get("side", "N/A"))
    profile    = order.get("profile", "N/A")
    user_id    = order.get("user_id", "N/A")
    order_id   = order.get("order_id", "N/A")
    reasonings = order.get("reasonings", "")

    risk       = order.get("risk_evaluation") or {}
    rr         = risk.get("actual_rr", "N/A")
    qty        = risk.get("suggested_qty", "N/A")
    risk_score = risk.get("risk_score", "N/A")
    rps        = risk.get("risk_per_share", "N/A")
    rwps       = risk.get("reward_per_share", "N/A")
    icon   = "✅"
    thesis = reasonings

    stats = (
        f"{'Qty:':<9}{str(qty):<10}R:R:    {rr}\n"
        f"{'Risk:':<9}{str(rps):<10}Reward: {rwps}\n"
        f"{'Score:':<9}{risk_score}/1"
    )

    text = (
        f"<b>{icon} Order EXECUTED — {symbol}</b>\n\n"
        f"Side:    <b>{action}</b> | Profile: <b>{profile}</b>\n"
        f"User:    <code>{user_id}</code>\n"
        f"<code>{stats}</code>\n"
        f"OrderID: <code>{order_id}</code>\n"
        f"\n<blockquote>{thesis}</blockquote>"
    )
    await _send(text, _THREAD_ORDER)
    print(f"   [📬 Telegram] Order posted | {symbol} {action}")
