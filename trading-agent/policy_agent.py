from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Literal, Optional

import ollama
from pydantic import BaseModel, Field, ValidationError


class LLMClient:
    """
    Abstract interface so you can swap LLM providers without changing PolicyAgent.
    """

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        Return raw text from the model (ideally JSON-only for easier parsing).
        """
        raise NotImplementedError


class OllamaLLMClient(LLMClient):
    """
    Ollama-backed LLM client.

    - model: e.g. "llama3.1" or any local model you pulled with `ollama pull`.
    - host: override if Ollama is not on the default localhost:11434.
    """

    def __init__(self, model: str = "llama3.1", host: Optional[str] = None):
        self.model = model
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        Use Ollama's chat API and return assistant content as a string.

        The PolicyAgent system prompt instructs the model to output ONLY JSON.
        If you want stricter guarantees, you can switch to `ollama.generate`
        with `format='json'` and parse the JSON directly. [web:84][web:88][web:92][web:98]
        """
        # Configure host via env for the ollama library
        os.environ.setdefault("OLLAMA_HOST", self.host)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Non-streaming chat call; returns dict with message.content. [web:84][web:88]
        response = ollama.chat(
            model=self.model,
            messages=messages,
        )

        content = response["message"]["content"]
        return content


# ---------- Pydantic schema for the agent output ----------


class TradeIntent(BaseModel):
    symbol: str
    side: Literal["long", "short"]
    entry_type: Literal["market", "limit"]
    entry_price: Optional[float] = None

    take_profit: Optional[float] = Field(
        None, description="Target exit price for profit"
    )
    stop_loss: Optional[float] = Field(None, description="Protective stop price")

    max_risk_pct: float = Field(1.0, ge=0.1, le=1.0)
    time_in_force: Literal["day", "gtc"] = "day"
    rationale: str = Field(..., min_length=10)


class PolicyOutput(BaseModel):
    # Pydantic v2: use list[...] + min_length/max_length on Field instead of conlist. [web:105][web:108]
    trades: List[TradeIntent] = Field(default_factory=list, max_length=5)


# ---------- Config + agent wrapper ----------


@dataclass
class PolicyAgentConfig:
    model: str = "llama3.1"  # informational only; actual model lives in the LLM client
    max_trades: int = 3
    whitelist: Optional[List[str]] = None  # if not None, only trade these symbols


class PolicyAgent:
    """
    RAG-aware policy agent:

    - Consumes text context (from your RAG pipeline + indicators snapshot).
    - Encodes a conservative trend-following strategy in the prompt:
      * Go LONG only when trend and sentiment are clearly positive.
      * Go SHORT only when both are clearly negative.
      * If signals conflict, propose no trade.
    - Enforces structure and risk constraints via Pydantic validation:
      * Reward-to-risk ratio >= 1.5 (checked by your risk engine, hinted in prompt).
      * max_risk_pct between 0.1% and 1.0% of equity as a guideline. [web:74][web:78]
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
- max_risk_pct represents the maximum percentage of account equity to risk on this single idea.
  It must be between 0.1 and 1.0 (meaning 0.1% to 1.0% of equity).
- Each trade must target a reward-to-risk ratio >= 1.5:
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
      "rationale": "detailed explanation explaining the trade"
    }}
  ]
}}

If you do not see any good trades, return:
{{ "trades": [] }}.
        """.strip()

    def _build_user_prompt(
        self,
        context: str,
        indicators_summary: str,
        account_equity: float,
    ) -> str:
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
- Prefer 'market' entries when momentum is strong; otherwise 'limit' entries around key levels.
        """.strip()

    def propose_trades(
        self,
        context: str,
        indicators_summary: str,
        account_equity: float,
    ) -> PolicyOutput:
        """
        Main entry point:

        - Builds prompts
        - Calls the LLM
        - Extracts and parses JSON
        - Validates against PolicyOutput schema
        - Applies optional symbol whitelist filter
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            context, indicators_summary, account_equity
        )

        raw = self.llm.generate(system_prompt, user_prompt)

        # Defensive: strip any non-JSON wrapper if the model adds explanations.
        json_str = self._extract_json(raw)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}\nRaw: {raw[:500]}")

        try:
            parsed = PolicyOutput(**data)
        except ValidationError as e:
            raise ValueError(f"Policy output failed schema validation: {e}")

        # Optional: enforce whitelist again at code level as additional safety.
        if self.config.whitelist is not None:
            filtered_trades = [
                t for t in parsed.trades if t.symbol in self.config.whitelist
            ]
            parsed = PolicyOutput(trades=filtered_trades)

        return parsed

    @staticmethod
    def _extract_json(raw: str) -> str:
        """
        Try to extract the JSON object from the LLM response.

        If the model is configured to return JSON-only, this just returns raw.
        Otherwise, it grabs the substring between the first '{' and the last '}'.
        """
        raw = raw.strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"Could not find JSON object in response: {raw[:500]}")
        return raw[start : end + 1]


# ---------- Quick local test harness ----------

if __name__ == "__main__":
    # Example of how you might instantiate and test the agent
    llm = OllamaLLMClient(model="llama3.1")
    cfg = PolicyAgentConfig(
        model="llama3.1",
        max_trades=3,
        whitelist=["AAPL", "NVDA", "MSFT"],
    )

    agent = PolicyAgent(llm_client=llm, config=cfg)

    # Dummy context for a dry run
    context = (
        "AAPL and NVDA are in strong uptrends with positive earnings surprises. "
        "MSFT shows mixed sentiment after guidance was revised lower."
    )
    indicators = (
        "AAPL: price above 50/200 MA, RSI 60. "
        "NVDA: price above 50/200 MA, RSI 65. "
        "MSFT: price near 200 MA, RSI 52."
    )
    equity = 100_000.0

    output = agent.propose_trades(
        context=context,
        indicators_summary=indicators,
        account_equity=equity,
    )
    print(output.model_dump())
