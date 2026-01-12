from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import json
import os

from pydantic import BaseModel, Field, ValidationError, conlist

# Replace this with your LLM client of choice (OpenAI, etc.)
# Here we declare a simple interface you can implement.
class LLMClient:
    def __init__(self, model: str):
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        Return raw LLM text response. You must implement this with your provider.
        It should return ONLY the JSON string for easier parsing.
        """
        raise NotImplementedError


# ---------- Pydantic schema for the agent output ----------

class TradeIntent(BaseModel):
    symbol: str = Field(..., description="Ticker symbol, e.g. AAPL")
    side: str = Field(..., regex="^(long|short)$")
    entry_type: str = Field(..., regex="^(market|limit)$")
    # If entry_type == 'market', entry_price can be None.
    entry_price: Optional[float] = Field(
        None, description="Limit entry price; null for market orders"
    )

    take_profit: float = Field(..., description="Target exit price for profit")
    stop_loss: float = Field(..., description="Protective stop price")

    # Meta fields for downstream risk engine
    max_risk_pct: float = Field(
        1.0,
        description="Maximum percentage of account equity to risk on this idea (0-1%)",
        ge=0.1,
        le=1.0,
    )
    time_in_force: str = Field(
        "day",
        description="Time in force, e.g. day, gtc",
        regex="^(day|gtc)$",
    )
    rationale: str = Field(
        ...,
        description="Short explanation of why this trade makes sense",
        min_length=10,
    )


class PolicyOutput(BaseModel):
    trades: conlist(TradeIntent, max_items=5)  # up to 5 trades per cycle


# ---------- Config + agent wrapper ----------

@dataclass
class PolicyAgentConfig:
    model: str = "gpt-4.1"  # placeholder; change to what you actually call
    max_trades: int = 3
    whitelist: Optional[List[str]] = None  # if not None, only trade these symbols


class PolicyAgent:
    """
    RAG-aware policy agent:
    - Consumes text context (from your RAG pipeline + indicators snapshot).
    - Returns a validated list of TradeIntent objects.
    """

    def __init__(self, llm_client: LLMClient, config: PolicyAgentConfig):
        self.llm = llm_client
        self.config = config

    def _build_system_prompt(self) -> str:
        return f"""
You are a cautious algorithmic trading assistant.

Your job:
- Read the market and portfolio context.
- Decide whether to open NEW positions only; you do not manage existing positions here.
- Return at most {self.config.max_trades} trade ideas as strict JSON matching the given schema.

Risk and strategy rules (non-negotiable):
- You are conservative: it is acceptable to output zero trades.
- Risk per trade (max_risk_pct) must be between 0.1 and 1.0 (meaning 0.1% to 1.0% of equity).
- Each trade must have a reward-to-risk ratio >= 1.5:
  - For a LONG: take_profit - entry_price >= 1.5 * (entry_price - stop_loss).
  - For a SHORT: stop_loss - entry_price >= 1.5 * (take_profit - entry_price).
- Side:
  - LONG only when both trend and sentiment are clearly positive.
  - SHORT only when both trend and sentiment are clearly negative.
  - If signals conflict or are unclear, DO NOT propose a trade.

Symbols:
- Only trade symbols that are explicitly mentioned in the context.
{f"- Additionally, only trade from this whitelist: {', '.join(self.config.whitelist)}." if self.config.whitelist else ""}

Output format:
- Output ONLY valid JSON with this shape (no extra text, no markdown):

{{
  "trades": [
    {{
      "symbol": "AAPL",
      "side": "long" or "short",
      "entry_type": "market" or "limit",
      "entry_price": 190.5 or null,
      "take_profit": 195.0,
      "stop_loss": 188.0,
      "max_risk_pct": 0.5,
      "time_in_force": "day" or "gtc",
      "rationale": "Short explanation..."
    }}
  ]
}}

If you do not see any good trades, return:
{{ "trades": [] }}.
        """.strip()

    def _build_user_prompt(self, context: str, indicators_summary: str, account_equity: float) -> str:
        return f"""
Context:
{context}

Indicators summary:
{indicators_summary}

Account:
- Approx equity: {account_equity:.2f} USD

Task:
- Propose at most {self.config.max_trades} trades that follow the risk and strategy rules.
- Use realistic prices based on the context.
- Prefer 'market' entries when momentum is strong; otherwise 'limit' around key levels.
        """.strip()

    def propose_trades(
        self,
        context: str,
        indicators_summary: str,
        account_equity: float,
    ) -> PolicyOutput:
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(context, indicators_summary, account_equity)

        raw = self.llm.generate(system_prompt, user_prompt)

        # Defensive: strip any non-JSON wrapper if your provider tends to add text.
        json_str = self._extract_json(raw)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}\nRaw: {raw[:500]}")

        try:
            parsed = PolicyOutput(**data)
        except ValidationError as e:
            raise ValueError(f"Policy output failed schema validation: {e}")

        # Optional: enforce whitelist at code level as additional safety.
        if self.config.whitelist is not None:
            filtered_trades = [
                t for t in parsed.trades if t.symbol in self.config.whitelist
            ]
            parsed = PolicyOutput(trades=filtered_trades)

        return parsed

    @staticmethod
    def _extract_json(raw: str) -> str:
        """
        Try to extract the JSON block from the LLM response.
        If the model is configured to return JSON-only, this can just be raw.
        """
        raw = raw.strip()
        # Simple heuristic: find first '{' and last '}'.
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"Could not find JSON object in response: {raw[:500]}")
        return raw[start : end + 1]
